"""Tests for controlled autonomy: dials, and trust earned from review decisions."""

from datetime import date

from exhale.autonomy import (
    AutonomyLevel,
    autonomy_settings,
    level_for,
    trust_record,
)
from exhale.schemas import ArtifactTier, ExtractionPayload
from exhale.store import HouseholdStore


def _pending(store, fam, title):
    return store.ingest(fam, ExtractionPayload(
        extracted_event=title, event_date=date(2026, 8, 10),
        action_required=True, confidence_score=0.95,
        artifact_tier=ArtifactTier.REMINDER,  # held pending → a decision to score
    ))


# --- settings ---------------------------------------------------------------------
def test_default_is_ask():
    assert autonomy_settings({}) == {"calendar_write": "ASK"}
    assert level_for({}, "calendar_write") is AutonomyLevel.ASK


def test_stored_setting_overrides_default():
    profile = {"autonomy": {"calendar_write": "AUTO"}}
    assert level_for(profile, "calendar_write") is AutonomyLevel.AUTO


def test_unknown_categories_in_profile_are_ignored():
    profile = {"autonomy": {"launch_rockets": "AUTO"}}
    assert "launch_rockets" not in autonomy_settings(profile)


# --- trust record -----------------------------------------------------------------
def test_confirmations_and_dismissals_score_the_record():
    store = HouseholdStore()
    dismissed = set()
    # 3 confirmed (right), 1 dismissed (wrong).
    for i in range(3):
        entry = _pending(store, "fam", f"Real thing {i}")
        store.correct("fam", entry.extraction_id)  # confirm-as-is
    wrong = _pending(store, "fam", "Marketing junk")
    dismissed.add(wrong.extraction_id)

    record = trust_record(store.ledger("fam"), dismissed)
    assert record["agreed"] == 3
    assert record["overruled"] == 1
    assert record["decisions"] == 4
    assert record["accuracy"] == 0.75
    assert record["eligible_for_auto"] is False  # below both bars


def test_correction_with_changes_counts_as_agreed_with_fixes():
    store = HouseholdStore()
    entry = _pending(store, "fam", "Camp")
    store.correct("fam", entry.extraction_id, event_date=date(2026, 8, 12))
    record = trust_record(store.ledger("fam"), set())
    assert record["agreed_with_fixes"] == 1
    assert record["agreed"] == 0


def test_strong_record_is_eligible_for_auto():
    store = HouseholdStore()
    for i in range(10):
        entry = _pending(store, "fam", f"Item {i}")
        store.correct("fam", entry.extraction_id)
    record = trust_record(store.ledger("fam"), set())
    assert record["decisions"] == 10
    assert record["accuracy"] == 1.0
    assert record["eligible_for_auto"] is True


def test_no_decisions_means_no_eligibility_and_null_accuracy():
    record = trust_record([], set())
    assert record["accuracy"] is None
    assert record["eligible_for_auto"] is False
