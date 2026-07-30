"""The Learning Scoreboard — the instrument for "is Exhale learning?"

The metric that governs Exhale is not engagement; it's whether the model of the
family is getting better. These tests hold that instrument to the same honesty
bar as the rest of the system: a cold start reads as a cold start, no pattern is
claimed below the evidence bar, and the surprise count moves only on a real
acknowledgement.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.learning import (
    MAX_ACK_ENTRIES,
    build_learning_scoreboard,
    record_learning_ack,
)
from exhale.schemas import ArtifactTier, ExtractionPayload
from exhale.store import HouseholdStore

client = TestClient(app)

BASE = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


def _ingest(store, fam, title, event, *, deadline=None, ref=None, at=None):
    entry = store.ingest(fam, ExtractionPayload(
        extracted_event=title, event_date=event, deadline_date=deadline,
        action_required=True, confidence_score=0.95,
        artifact_tier=ArtifactTier.CONFIRMATION,
        source_reference=ref or f"m_{event.isoformat()}",
    ))
    if at is not None:  # pin ingestion time so time-to-first-pattern is deterministic
        entry.created_at = at
    return entry


def _isla_weeks(store, fam, *, offsets_days=(0, 3, 7)):
    """Three weekly ISLA Mondays, ingested at the given day-offsets from BASE."""

    mondays = (date(2026, 6, 22), date(2026, 6, 29), date(2026, 7, 6))
    for monday, off in zip(mondays, offsets_days):
        wed_before = date.fromordinal(monday.toordinal() - 5)
        _ingest(store, fam, f"ISLA Camp this Week {monday.month}/{monday.day}",
                monday, deadline=wed_before, at=BASE + timedelta(days=off))


# --- cold start -------------------------------------------------------------------
def test_cold_start_is_honest_not_padded():
    board = build_learning_scoreboard([], {}, None, now=BASE)
    assert board["data"] == {
        "signals_seen": 0, "first_seen": None, "last_seen": None, "days_observed": 0}
    assert board["time_to_first_pattern"] == {"achieved": False}
    assert board["patterns_held"] == {"count": 0, "rules": [], "emerging": []}
    assert board["coverage_foresight"] is None   # no model → nothing to measure
    assert board["surprises"] == {"confirmed": 0, "this_week": 0, "latest": None}


# --- time to first pattern --------------------------------------------------------
def test_time_to_first_pattern_measures_the_real_moment():
    store = HouseholdStore()
    _isla_weeks(store, "fam", offsets_days=(0, 3, 7))
    board = build_learning_scoreboard(store.ledger("fam"), {}, now=BASE + timedelta(days=8))
    ttfp = board["time_to_first_pattern"]
    assert ttfp["achieved"] is True
    assert ttfp["signals_needed"] == 3      # the third occurrence is what crossed the bar
    assert ttfp["days"] == 7                 # BASE+7 minus BASE
    assert ttfp["first_pattern"]["kind"] in ("WEEKLY_CADENCE", "DEADLINE_LEAD")


def test_signals_needed_counts_noise_before_the_pattern():
    store = HouseholdStore()
    # Two unrelated one-off items arrive first, then the three ISLA weeks.
    _ingest(store, "fam", "Dentist reminder", date(2026, 6, 10), at=BASE)
    _ingest(store, "fam", "Field trip form", date(2026, 6, 12), at=BASE + timedelta(days=1))
    _isla_weeks(store, "fam", offsets_days=(2, 4, 6))
    ttfp = build_learning_scoreboard(store.ledger("fam"), {}).get("time_to_first_pattern")
    # Five signals had to flow before the first rule became knowable.
    assert ttfp["achieved"] is True
    assert ttfp["signals_needed"] == 5


def test_two_samples_are_emerging_not_a_pattern():
    store = HouseholdStore()
    _isla_weeks(store, "fam", offsets_days=(0, 3))  # only two weeks so far
    board = build_learning_scoreboard(store.ledger("fam"), {}, now=BASE + timedelta(days=4))
    assert board["time_to_first_pattern"]["achieved"] is False
    assert board["patterns_held"]["count"] == 0
    (emerging,) = board["patterns_held"]["emerging"]
    assert emerging == {"subject": "isla camp", "samples": 2, "needs": 1}


def test_held_pattern_is_not_also_listed_as_emerging():
    store = HouseholdStore()
    _isla_weeks(store, "fam")
    held = build_learning_scoreboard(store.ledger("fam"), {})["patterns_held"]
    assert held["count"] >= 1
    assert held["emerging"] == []          # a held subject never double-counts
    assert all(r["evidence"] for r in held["rules"])  # every rule cites its witnesses


def test_days_observed_tracks_age_of_first_signal():
    store = HouseholdStore()
    _ingest(store, "fam", "Anything", date(2026, 6, 10), at=BASE)
    board = build_learning_scoreboard(store.ledger("fam"), {}, now=BASE + timedelta(days=12, hours=5))
    assert board["data"]["signals_seen"] == 1
    assert board["data"]["days_observed"] == 12


# --- coverage foresight -----------------------------------------------------------
def test_coverage_foresight_reports_earliest_lead_and_acted_on():
    care_watch = {"gaps": [
        {"hours_until": 96.0}, {"hours_until": 30.5}, {"hours_until": 200.0}]}
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    profile = {"resolved_log": [
        {"item_id": "g1", "resolved_type": "dependency_gap",
         "resolved_at": (now.replace(tzinfo=None) - timedelta(days=2)).isoformat()},
        {"item_id": "g2", "resolved_type": "dependency_gap",
         "resolved_at": (now.replace(tzinfo=None) - timedelta(days=10)).isoformat()},  # too old
        {"item_id": "w1", "resolved_type": "waiting_on",
         "resolved_at": (now.replace(tzinfo=None) - timedelta(days=1)).isoformat()},   # wrong type
    ]}
    cf = build_learning_scoreboard([], profile, care_watch, now=now)["coverage_foresight"]
    assert cf["gaps_ahead"] == 3
    assert cf["earliest_lead_hours"] == 30.5     # soonest gap seen this far ahead
    assert cf["acted_on_this_week"] == 1         # only the recent dependency_gap counts


def test_coverage_foresight_none_without_a_model():
    assert build_learning_scoreboard([], {}, None)["coverage_foresight"] is None


# --- surprises: the metric that must never be fabricated --------------------------
def test_surprise_only_counts_after_a_real_ack():
    store = HouseholdStore()
    fam = "fam_surprise"
    # Before any acknowledgement, the magic metric is honestly zero.
    assert build_learning_scoreboard([], store.profile(fam))["surprises"]["confirmed"] == 0

    record_learning_ack(store, fam, observation_id="rule:isla camp",
                        observation_type="learned_rule", note="had no idea")
    surprises = build_learning_scoreboard([], store.profile(fam))["surprises"]
    assert surprises["confirmed"] == 1
    assert surprises["this_week"] == 1
    assert surprises["latest"]["note"] == "had no idea"


def test_ack_is_idempotent_per_observation():
    store = HouseholdStore()
    fam = "fam_ack_dupe"
    first = record_learning_ack(store, fam, observation_id="gap:2026-08-01",
                                observation_type="coverage_gap")
    dupe = record_learning_ack(store, fam, observation_id="gap:2026-08-01",
                               observation_type="coverage_gap")
    assert first is not None and dupe is None            # second tap is a no-op
    assert len(store.profile(fam)["learning_acks"]) == 1


def test_ack_rejects_unknown_observation_type():
    with pytest.raises(ValueError):
        record_learning_ack(HouseholdStore(), "fam", observation_id="x",
                            observation_type="mind_reading")


def test_old_surprises_still_count_but_not_this_week():
    store = HouseholdStore()
    fam = "fam_old_surprise"
    old = datetime.now(timezone.utc) - timedelta(days=20)
    record_learning_ack(store, fam, observation_id="rule:old",
                        observation_type="learned_rule", acknowledged_at=old)
    surprises = build_learning_scoreboard([], store.profile(fam))["surprises"]
    assert surprises["confirmed"] == 1
    assert surprises["this_week"] == 0   # counted all-time, not in the weekly slice


def test_ack_log_is_capped():
    store = HouseholdStore()
    fam = "fam_ack_cap"
    for i in range(MAX_ACK_ENTRIES + 15):
        record_learning_ack(store, fam, observation_id=f"obs_{i}",
                            observation_type="learned_rule")
    assert len(store.profile(fam)["learning_acks"]) == MAX_ACK_ENTRIES


# --- the trust ledger: is Exhale right, not just learning? ------------------------
def test_trust_cold_start_has_no_score():
    trust = build_learning_scoreboard([], {})["trust"]
    assert trust["asserted"] == 0
    assert trust["confident_accuracy"] is None  # nothing scored ≠ perfect score


def test_uncorrected_assertions_score_full_trust():
    store = HouseholdStore()
    _isla_weeks(store, "fam")  # three HIGH-band auto-commits, untouched
    trust = build_learning_scoreboard(store.ledger("fam"), store.profile("fam"))["trust"]
    assert trust["asserted"] == 3
    assert trust["corrected"] == 0
    assert trust["confident_accuracy"] == 1.0


def test_a_real_correction_lowers_confident_accuracy():
    store = HouseholdStore()
    _isla_weeks(store, "fam")
    first = store.ledger("fam")[0]
    # The user fixes the date — Exhale was confidently wrong about this one.
    store.correct("fam", first.extraction_id, event_date=date(2026, 6, 23))
    trust = build_learning_scoreboard(store.ledger("fam"), store.profile("fam"))["trust"]
    assert trust["corrected"] == 1
    # The correcting entry is USER_CONFIRMED ground truth, not a new assertion.
    assert trust["asserted"] == 3
    assert trust["confident_accuracy"] == round(1 - 1 / 3, 3)


def test_confirmation_without_changes_is_agreement_not_failure():
    store = HouseholdStore()
    _isla_weeks(store, "fam")
    first = store.ledger("fam")[0]
    store.correct("fam", first.extraction_id)  # confirm as-is — no fixes
    trust = build_learning_scoreboard(store.ledger("fam"), store.profile("fam"))["trust"]
    assert trust["corrected"] == 0
    assert trust["confident_accuracy"] == 1.0


def test_trust_carries_the_review_side_record():
    store = HouseholdStore()
    profile = {"dismissed_extractions": ["ext_a", "ext_b"]}
    trust = build_learning_scoreboard(store.ledger("fam"), profile)["trust"]
    assert trust["review"]["overruled"] == 2  # exhale.autonomy's scored record


# --- API --------------------------------------------------------------------------
def test_learning_endpoint_cold_family_is_valid():
    board = client.get("/v1/families/fam_learn_cold/learning").json()
    assert board["view"] == "learning_scoreboard"
    assert board["time_to_first_pattern"] == {"achieved": False}
    assert board["surprises"]["confirmed"] == 0


def test_learning_endpoint_surfaces_a_held_pattern():
    fam = "fam_learn_pattern"
    for monday in (date(2026, 6, 22), date(2026, 6, 29), date(2026, 7, 6)):
        client.post(f"/v1/families/{fam}/extractions", json={
            "extracted_event": f"ISLA Camp this Week {monday.month}/{monday.day}",
            "event_date": monday.isoformat(),
            "deadline_date": date.fromordinal(monday.toordinal() - 5).isoformat(),
            "action_required": True, "confidence_score": 0.96,
        })
    board = client.get(f"/v1/families/{fam}/learning").json()
    assert board["data"]["signals_seen"] == 3
    assert board["patterns_held"]["count"] >= 1
    assert board["time_to_first_pattern"]["achieved"] is True


def test_ack_endpoint_moves_the_surprise_count():
    fam = "fam_learn_ack"
    r = client.post(f"/v1/families/{fam}/learning/ack", json={
        "observation_id": "rule:tuesday pickup", "observation_type": "learned_rule",
        "note": "didn't realize it was always me"})
    assert r.status_code == 200 and r.json()["acknowledged"] is True

    # Second identical ack is idempotent — the count can't be gamed.
    again = client.post(f"/v1/families/{fam}/learning/ack", json={
        "observation_id": "rule:tuesday pickup", "observation_type": "learned_rule"})
    assert again.json()["acknowledged"] is False

    board = client.get(f"/v1/families/{fam}/learning").json()
    assert board["surprises"]["confirmed"] == 1


def test_ack_endpoint_rejects_unknown_type():
    r = client.post("/v1/families/fam_learn_badack/learning/ack", json={
        "observation_id": "x", "observation_type": "telepathy"})
    assert r.status_code == 400
