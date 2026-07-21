"""Tests for the Layer-4 memory engine (learned recurring rules).

The central fixture mirrors the real pattern that motivated the engine: ISLA
summer camp recurs weekly on Mondays, and registration closes the Wednesday
before — a rule no single email states.
"""

from datetime import date

from exhale.memory import _stem, learn_rules
from exhale.schemas import ArtifactTier, ExtractionPayload
from exhale.store import HouseholdStore


def _ingest(store, fam, title, event, deadline=None, ref=None):
    return store.ingest(fam, ExtractionPayload(
        extracted_event=title, event_date=event, deadline_date=deadline,
        action_required=True, confidence_score=0.95,
        artifact_tier=ArtifactTier.CONFIRMATION,
        source_reference=ref or f"m_{event.isoformat()}",
    ))


def _isla_store():
    """Three weekly ISLA sessions, each with a Wednesday-before deadline."""

    store = HouseholdStore()
    for monday in (date(2026, 6, 22), date(2026, 6, 29), date(2026, 7, 6)):
        wednesday_before = date.fromordinal(monday.toordinal() - 5)
        _ingest(store, "fam", f"ISLA Camp this Week {monday.month}/{monday.day}",
                monday, wednesday_before)
    return store


# --- stemming ---------------------------------------------------------------------
def test_stem_collapses_recurring_instances():
    assert _stem("ISLA Camp this Week 7/13") == _stem("ISLA Camp this Week 7/20")
    assert _stem("ISLA Camp this Week 7/13") == "isla camp"


# --- weekly cadence ---------------------------------------------------------------
def test_learns_weekly_monday_cadence():
    rules = learn_rules(_isla_store().ledger("fam"))
    cadence = [r for r in rules if r.kind == "WEEKLY_CADENCE"]
    assert len(cadence) == 1
    assert cadence[0].subject == "isla camp"
    assert "Mondays" in cadence[0].detail
    assert cadence[0].samples == 3
    assert len(cadence[0].evidence) == 3  # every rule cites its witnesses


def test_learns_the_wednesday_before_deadline_rule():
    # The exact rule the family discovered by missing it.
    rules = learn_rules(_isla_store().ledger("fam"))
    lead = [r for r in rules if r.kind == "DEADLINE_LEAD"]
    assert len(lead) == 1
    assert "5 days before" in lead[0].detail
    assert "Wednesday" in lead[0].detail


def test_two_samples_do_not_make_a_rule():
    store = HouseholdStore()
    for monday in (date(2026, 6, 22), date(2026, 6, 29)):
        _ingest(store, "fam", "ISLA Camp", monday)
    assert learn_rules(store.ledger("fam")) == []


def test_skipped_week_still_counts_as_weekly_cadence():
    store = HouseholdStore()
    # Mondays with a two-week gap in the middle (vacation week skipped).
    for monday in (date(2026, 6, 22), date(2026, 6, 29), date(2026, 7, 13)):
        _ingest(store, "fam", "ISLA Camp", monday)
    rules = learn_rules(store.ledger("fam"))
    assert any(r.kind == "WEEKLY_CADENCE" for r in rules)


def test_mixed_weekdays_teach_nothing():
    store = HouseholdStore()
    for d in (date(2026, 6, 22), date(2026, 6, 30), date(2026, 7, 8)):  # Mon/Tue/Wed
        _ingest(store, "fam", "Random Thing", d)
    assert learn_rules(store.ledger("fam")) == []


def test_inconsistent_deadline_leads_teach_nothing():
    store = HouseholdStore()
    _ingest(store, "fam", "Camp", date(2026, 6, 22), date(2026, 6, 17))  # 5 days
    _ingest(store, "fam", "Camp", date(2026, 6, 29), date(2026, 6, 26))  # 3 days
    _ingest(store, "fam", "Camp", date(2026, 7, 6), date(2026, 7, 3))    # 3 days
    rules = learn_rules(store.ledger("fam"))
    assert not any(r.kind == "DEADLINE_LEAD" for r in rules)  # never average guesses


def test_resent_email_does_not_double_witness():
    store = _isla_store()
    # The same June 22 session announced twice (a resend).
    _ingest(store, "fam", "ISLA Camp this Week 6/22", date(2026, 6, 22),
            date(2026, 6, 17), ref="resend")
    rules = learn_rules(store.ledger("fam"))
    cadence = next(r for r in rules if r.kind == "WEEKLY_CADENCE")
    assert cadence.samples == 3  # still three occurrences, not four
