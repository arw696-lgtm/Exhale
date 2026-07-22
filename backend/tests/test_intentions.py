"""Personal intentions + the Time For What Matters briefing block."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.intentions import (
    build_time_for_what_matters,
    new_intention,
    open_items,
    record_follow_up,
    set_status,
    surface,
)

client = TestClient(app)

NOW = datetime(2026, 7, 22, 9, 0)


def _weeks(n: int) -> timedelta:
    return timedelta(days=7 * n)


# --- the module -------------------------------------------------------------------
def test_new_intention_shape_and_validation():
    item = new_intention("fam_x", "Andy", "See Mark", type_="standing")
    assert item["status"] == "open"
    assert item["type"] == "standing"
    assert item["created_by"] == "Andy"
    assert item["family_id"] == "fam_x"
    with pytest.raises(ValueError):
        new_intention("fam_x", "Andy", "   ")
    with pytest.raises(ValueError):
        new_intention("fam_x", "Andy", "Gym", type_="someday_maybe")


def test_set_status_transitions_and_errors():
    items = [new_intention("f", "Andy", "Gym")]
    iid = items[0]["intention_id"]
    items = set_status(items, iid, "matched")
    assert items[0]["status"] == "matched"
    items = set_status(items, iid, "open")  # a standing intent reopens
    assert items[0]["status"] == "open"
    with pytest.raises(ValueError):
        set_status(items, iid, "done")
    with pytest.raises(KeyError):
        set_status(items, "int_nope", "matched")


def test_block_counts_and_open_filter():
    items = [new_intention("f", "A", "Gym"),
             new_intention("f", "A", "Dermatologist", type_="one_off")]
    items = set_status(items, items[1]["intention_id"], "matched", now=NOW)
    items, groups = surface(items, now=NOW)
    block = build_time_for_what_matters([{"start": "2026-07-23T13:00:00"}],
                                        groups, items)
    assert block["counts"]["windows"] == 1
    assert block["counts"]["open"] == 1
    assert block["counts"]["matched"] == 1
    assert block["counts"]["dismissed"] == 0
    assert [i["description"] for i in block["open_intentions"]] == ["Gym"]
    assert open_items(items)[0]["description"] == "Gym"


# --- staleness (anti-guilt) --------------------------------------------------------
def test_surfacing_is_weekly_debounced():
    items = [new_intention("f", "A", "Gym")]
    # Four page loads on the same day = ONE surfacing, not four.
    for _ in range(4):
        items, groups = surface(items, now=NOW)
    assert items[0]["surfaced_count"] == 1
    assert groups["active"], "still in the main list"


def test_four_weeks_unanswered_becomes_a_checkin_then_stale():
    items = [new_intention("f", "A", "See Mark")]
    # Four weekly surfacings — still active each time.
    for week in range(4):
        items, groups = surface(items, now=NOW + _weeks(week))
        assert groups["active"] and not groups["check_ins"]
    assert items[0]["surfaced_count"] == 4

    # Week 5: no more quiet nagging — one gentle check-in instead.
    items, groups = surface(items, now=NOW + _weeks(4))
    assert groups["active"] == []
    assert [i["description"] for i in groups["check_ins"]] == ["See Mark"]

    # Ignored for a week → retired quietly, surfaces nowhere.
    items, groups = surface(items, now=NOW + _weeks(5) + timedelta(days=1))
    assert items[0]["status"] == "stale"
    assert groups["active"] == [] and groups["check_ins"] == []


def test_reconfirm_resets_the_staleness_clock():
    items = [new_intention("f", "A", "See Mark")]
    for week in range(5):
        items, groups = surface(items, now=NOW + _weeks(week))
    assert groups["check_ins"], "in check-in territory"

    from exhale.intentions import reconfirm

    items = reconfirm(items, items[0]["intention_id"])
    assert items[0]["surfaced_count"] == 0
    assert items[0]["check_in_at"] is None
    items, groups = surface(items, now=NOW + _weeks(5))
    assert groups["active"], "back in the main list with a fresh clock"


# --- the one follow-up -------------------------------------------------------------
def test_matched_intention_gets_one_followup_then_no_response():
    items = [new_intention("f", "A", "Ali's dermatology appointment", type_="one_off")]
    iid = items[0]["intention_id"]
    items = set_status(items, iid, "matched",
                       matched_window={"start": "2026-07-23T13:00:00",
                                       "end": "2026-07-23T15:00:00"}, now=NOW)
    assert items[0]["matched_at"] is not None

    # Too soon — no follow-up yet.
    items, groups = surface(items, now=NOW + timedelta(days=3))
    assert groups["follow_ups"] == []

    # A week later: asked once, with the window it referred to.
    items, groups = surface(items, now=NOW + _weeks(1))
    (fu,) = groups["follow_ups"]
    assert fu["description"] == "Ali's dermatology appointment"
    assert fu["matched_window"]["start"] == "2026-07-23T13:00:00"

    # Ignored for another week → logged no_response, never asked again.
    items, groups = surface(items, now=NOW + _weeks(2) + timedelta(days=1))
    assert items[0]["follow_up_outcome"] == "no_response"
    assert groups["follow_ups"] == []


def test_followup_answer_is_logged_once_only():
    items = [new_intention("f", "A", "Gym")]
    iid = items[0]["intention_id"]
    with pytest.raises(ValueError):  # not matched → no follow-up exists
        record_follow_up(items, iid, "happened")
    items = set_status(items, iid, "matched", now=NOW)
    items = record_follow_up(items, iid, "happened")
    assert items[0]["follow_up_outcome"] == "happened"
    with pytest.raises(ValueError):  # once, then done
        record_follow_up(items, iid, "didnt_happen")
    with pytest.raises(ValueError):  # bad outcome value
        record_follow_up(items, iid, "maybe")
    # An answered follow-up never resurfaces.
    items, groups = surface(items, now=NOW + _weeks(3))
    assert groups["follow_ups"] == []


# --- the API ------------------------------------------------------------------------
def _household_with_windows(fam: str) -> None:
    """One caregiver working 9–15 with school covering 9–15 → real free windows."""

    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{
            "recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                          "supervised_end": "18:00:00"},
            "school": {"name": "ISLA", "first_day": "2020-01-01",
                       "last_day": "2030-12-31", "school_start": "09:00:00",
                       "school_end": "15:00:00"},
        }],
        "caregivers": [{"name": "Andy"}],
    })


def test_intentions_roundtrip_and_status():
    fam = "fam_intentions_api"
    r = client.post(f"/v1/families/{fam}/intentions",
                    json={"description": "See Mark", "type": "standing"})
    assert r.status_code == 200
    iid = r.json()["intention_id"]
    assert r.json()["created_by"] == "household"  # anonymous dev mode default

    assert client.post(f"/v1/families/{fam}/intentions",
                       json={"description": "", "type": "standing"}).status_code == 400

    listing = client.get(f"/v1/families/{fam}/intentions").json()
    assert listing["count"] == 1

    assert client.post(f"/v1/families/{fam}/intentions/{iid}/status",
                       json={"status": "matched"}).status_code == 200
    assert client.post(f"/v1/families/{fam}/intentions/{iid}/status",
                       json={"status": "later"}).status_code == 400
    assert client.post(f"/v1/families/{fam}/intentions/int_ghost/status",
                       json={"status": "matched"}).status_code == 404


def test_briefing_lays_windows_next_to_intentions():
    fam = "fam_tfwm_full"
    _household_with_windows(fam)
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Ali's dermatology appointment", "type": "one_off"})
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "See Mark", "type": "standing"})

    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["open"] == 2
    # Real windows from the engine's own ranking (school-covered weekday hours).
    assert block["counts"]["windows"] >= 1
    assert all(w["caregiver"] == "Andy" for w in block["windows"])
    descriptions = {i["description"] for i in block["open_intentions"]}
    assert descriptions == {"Ali's dermatology appointment", "See Mark"}


def test_matched_intention_leaves_the_block():
    fam = "fam_tfwm_matched"
    _household_with_windows(fam)
    iid = client.post(f"/v1/families/{fam}/intentions",
                      json={"description": "Gym", "type": "standing"}).json()["intention_id"]
    client.post(f"/v1/families/{fam}/intentions/{iid}/status", json={"status": "matched"})
    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["open"] == 0
    assert block["counts"]["matched"] == 1
    assert block["open_intentions"] == []


def test_intentions_without_coverage_model_still_surface():
    fam = "fam_tfwm_nomodel"
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Call grandma", "type": "standing"})
    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["windows"] == 0
    assert block["counts"]["open"] == 1


def test_untouched_family_has_no_block_at_all():
    fam = "fam_tfwm_silent"
    assert client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"] is None


def test_api_matched_window_reconfirm_and_followup_endpoints():
    fam = "fam_tfwm_lifecycle"
    iid = client.post(f"/v1/families/{fam}/intentions",
                      json={"description": "Gym", "type": "standing"}).json()["intention_id"]

    # Matched with the window it went to.
    r = client.post(f"/v1/families/{fam}/intentions/{iid}/status", json={
        "status": "matched",
        "window_start": "2026-07-23T13:00:00", "window_end": "2026-07-23T15:00:00"})
    assert r.status_code == 200
    stored = client.get(f"/v1/families/{fam}/intentions").json()["intentions"][0]
    assert stored["matched_at"] is not None
    assert stored["matched_window"] == {"start": "2026-07-23T13:00:00",
                                        "end": "2026-07-23T15:00:00"}

    # The one follow-up: answer once, then 400 on a repeat; 404 for a ghost.
    assert client.post(f"/v1/families/{fam}/intentions/{iid}/follow-up",
                       json={"outcome": "happened"}).status_code == 200
    assert client.post(f"/v1/families/{fam}/intentions/{iid}/follow-up",
                       json={"outcome": "happened"}).status_code == 400
    assert client.post(f"/v1/families/{fam}/intentions/int_ghost/follow-up",
                       json={"outcome": "happened"}).status_code == 404

    # Reconfirm brings it back open with a fresh clock.
    assert client.post(f"/v1/families/{fam}/intentions/{iid}/reconfirm").status_code == 200
    stored = client.get(f"/v1/families/{fam}/intentions").json()["intentions"][0]
    assert stored["status"] == "open"
    assert stored["surfaced_count"] == 0


def test_add_nudge_shows_once_not_weekly():
    fam = "fam_tfwm_nudge"
    _household_with_windows(fam)  # a model, but no intentions logged
    first = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert first["show_add_nudge"] is True
    second = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert second["show_add_nudge"] is False  # shown once, never a weekly nag
