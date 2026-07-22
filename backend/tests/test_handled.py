"""The resolved-items log + "What Exhale Handled This Week" recap."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.handled import (
    MAX_LOG_ENTRIES,
    handled_this_week,
    log_resolved,
)
from exhale.store import HouseholdStore

client = TestClient(app)


# --- the log --------------------------------------------------------------------
def test_log_resolved_appends_and_dedupes():
    store = HouseholdStore()
    fam = "fam_log"
    entry = log_resolved(store, fam, item_id="ob_1", resolved_type="dependency_gap",
                         brief_description="Permission slip — handled")
    assert entry["resolved_type"] == "dependency_gap"
    # Same item+type again → no duplicate, recap never inflates.
    assert log_resolved(store, fam, item_id="ob_1", resolved_type="dependency_gap",
                        brief_description="Permission slip — handled") is None
    assert len(store.profile(fam)["resolved_log"]) == 1


def test_log_resolved_rejects_unknown_type():
    store = HouseholdStore()
    with pytest.raises(ValueError):
        log_resolved(store, "fam", item_id="x", resolved_type="victory_lap",
                     brief_description="nope")


def test_log_is_capped():
    store = HouseholdStore()
    fam = "fam_cap"
    for i in range(MAX_LOG_ENTRIES + 25):
        log_resolved(store, fam, item_id=f"ob_{i}", resolved_type="waiting_on",
                     brief_description=f"item {i}")
    log = store.profile(fam)["resolved_log"]
    assert len(log) == MAX_LOG_ENTRIES
    assert log[-1]["item_id"] == f"ob_{MAX_LOG_ENTRIES + 24}"  # newest kept


# --- the recap ------------------------------------------------------------------
def test_handled_this_week_windows_and_sorts():
    store = HouseholdStore()
    fam = "fam_recap"
    now = datetime(2026, 7, 21, 12, 0)
    log_resolved(store, fam, item_id="old", resolved_type="waiting_on",
                 brief_description="ancient history",
                 resolved_at=now - timedelta(days=9))
    log_resolved(store, fam, item_id="mid", resolved_type="dependency_gap",
                 brief_description="camp registration — handled",
                 resolved_at=now - timedelta(days=5))
    log_resolved(store, fam, item_id="new", resolved_type="waiting_on",
                 brief_description="dentist thread (loop closed)",
                 resolved_at=now - timedelta(hours=3))

    recap = handled_this_week(store.profile(fam), now=now)
    assert recap["count"] == 2  # nine-day-old entry excluded
    assert [e["item_id"] for e in recap["items"]] == ["new", "mid"]  # newest first


def test_quiet_week_is_zero_not_fabricated():
    recap = handled_this_week({}, now=datetime(2026, 7, 21))
    assert recap == {"view": "handled_recap", "days": 7, "count": 0, "items": []}


# --- the hooks (API) --------------------------------------------------------------
def _committed_obligation(fam: str) -> str:
    """Commit an obligation whose deadline is 5 days out → 🟡 IMPORTANT band."""

    from datetime import date as _date

    soon = _date.today() + timedelta(days=5)
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Camp registration",
        "target_person_name": "Stevie",
        "event_date": (soon + timedelta(days=10)).isoformat(),
        "deadline_date": soon.isoformat(),
        "action_required": True,
        "confidence_score": 0.97,
    })
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    return next(e["obligation_node_id"] for e in ledger if e["obligation_node_id"])


def test_approving_a_draft_logs_the_catch_into_the_briefing():
    fam = "fam_handled_approve"
    ob_id = _committed_obligation(fam)
    r = client.post(f"/v1/families/{fam}/actions/approve",
                    json={"obligation_node_id": ob_id})
    assert r.status_code == 200

    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1
    (item,) = handled["items"]
    assert item["resolved_type"] == "dependency_gap"
    assert "Camp registration" in item["brief_description"]
    assert "Stevie" in item["brief_description"]

    # Approving again (idempotent resolution) never double-logs.
    client.post(f"/v1/families/{fam}/actions/approve",
                json={"obligation_node_id": ob_id})
    assert client.get(f"/v1/families/{fam}/briefing").json()["handled"]["count"] == 1


def test_confirming_a_pending_item_logs_the_catch():
    fam = "fam_handled_confirm"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Soccer photo day",
        "event_date": "2026-09-20",
        "action_required": True,
        "confidence_score": 0.80,  # PENDING_VERIFICATION band
    })
    eid = client.get(f"/v1/families/{fam}/review").json()["pending"][0]["extraction_id"]
    assert client.post(f"/v1/families/{fam}/extractions/{eid}/confirm").status_code == 200

    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1
    assert "Soccer photo day" in handled["items"][0]["brief_description"]
    assert "confirmed by you" in handled["items"][0]["brief_description"]


def test_resolving_a_wait_logs_the_closed_loop():
    fam = "fam_handled_wait"
    item = client.post(f"/v1/families/{fam}/waiting", json={
        "who": "Dentist office", "about": "reschedule Stevie's cleaning",
    }).json()
    client.post(f"/v1/families/{fam}/waiting/{item['id']}/resolve")

    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1
    entry = handled["items"][0]
    assert entry["resolved_type"] == "waiting_on"
    assert "Dentist office" in entry["brief_description"]
    assert "loop closed" in entry["brief_description"]


def test_untouched_family_has_honest_quiet_recap():
    fam = "fam_handled_quiet"
    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 0
    assert handled["items"] == []
    # Nothing open either → the UI may honestly say "a quiet week".
    assert handled["open_urgent"] == 0


def test_zero_resolved_with_open_urgent_items_is_not_a_quiet_week():
    """A week where the system is behind must never read as calm."""

    fam = "fam_handled_behind"
    _committed_obligation(fam)  # open 🔴/🟡 gap, nothing resolved yet
    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    assert (briefing["summary"]["critical_count"]
            + briefing["summary"]["dependency_watch_count"]) >= 1
    handled = briefing["handled"]
    assert handled["count"] == 0
    assert handled["open_urgent"] >= 1  # UI shows the neutral line, not "quiet"


def test_open_urgent_counts_care_gaps_and_stale_waits():
    fam = "fam_handled_urgent_mix"
    # A child uncovered while the only caregiver works every day → 🔴 gaps.
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{"recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                                    "supervised_end": "18:00:00"}}],
        "caregivers": [{"name": "Andy", "work_pattern": {
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "08:00:00",
            "end": "18:00:00", "basis": "OBSERVED"}}],
    })
    # A wait that has gone critically stale (>14 days of silence).
    client.post(f"/v1/families/{fam}/waiting", json={
        "who": "Hennepin County", "about": "arborist follow-up",
        "since": "2026-06-01",
    })
    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 0
    assert handled["open_urgent"] >= 2  # care gaps + the stale wait both count


def test_resolving_everything_restores_the_quiet_week():
    fam = "fam_handled_requiet"
    ob_id = _committed_obligation(fam)
    before = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert before["open_urgent"] >= 1
    client.post(f"/v1/families/{fam}/actions/approve",
                json={"obligation_node_id": ob_id})
    after = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert after["count"] == 1       # the catch is remembered...
    assert after["open_urgent"] == 0  # ...and nothing urgent remains open
