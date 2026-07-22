"""Personal intentions + the Time For What Matters briefing block."""

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.intentions import (
    build_time_for_what_matters,
    new_intention,
    open_items,
    set_status,
)

client = TestClient(app)


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
    items = set_status(items, items[1]["intention_id"], "matched")
    block = build_time_for_what_matters([{"start": "2026-07-23T13:00:00"}], items)
    assert block["counts"] == {"windows": 1, "open": 1, "matched": 1, "dismissed": 0}
    assert [i["description"] for i in block["open_intentions"]] == ["Gym"]
    assert open_items(items)[0]["description"] == "Gym"


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
