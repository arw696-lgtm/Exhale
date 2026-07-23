"""Together-time windows: when both parents are free AND the kids are covered.

Newly computable now that both parents' calendars coexist (per-member
connections). The math must exclude EVERY going-out caregiver from what's
covering the children — a window only counts if someone/something else has them.
"""

from datetime import date, datetime, time

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.coverage import (
    Caregiver,
    CareRecipient,
    CoverageEngine,
    FamilyCoverage,
    SchoolCalendar,
    WorkPattern,
)
from exhale.schemas import FactOrigin

client = TestClient(app)

MONDAY = date(2026, 9, 14)          # a school day
NOW = datetime(2026, 9, 13, 20, 0)  # the night before


def _school():
    return SchoolCalendar(name="ISLA", first_day=date(2026, 9, 1),
                          last_day=date(2027, 6, 3),
                          school_start=time(9, 0), school_end=time(15, 0))


def _family(caregivers, *, school=True):
    engine = CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), caregivers,
        school=_school() if school else None, now=NOW)
    return FamilyCoverage([engine])


def test_both_free_during_school_is_a_together_window():
    # Neither parent works → both free all day; school covers 9–3.
    andy = Caregiver(name="Andy", role="PARENT")
    ali = Caregiver(name="Ali", role="PARENT")
    fam = _family([andy, ali])
    windows = fam.shared_windows(["Andy", "Ali"], MONDAY, MONDAY, min_hours=1.0)
    # The together window is exactly school hours (when someone else has Stevie).
    assert len(windows) == 1
    assert windows[0].start.time() == time(9, 0)
    assert windows[0].end.time() == time(15, 0)
    assert any("ISLA" in label for label in windows[0].child_covered_by)


def test_one_parent_working_kills_the_together_window():
    # Ali works 9–3 → the two are never simultaneously free during coverage.
    andy = Caregiver(name="Andy", role="PARENT")
    ali = Caregiver(name="Ali", role="PARENT", work_pattern=WorkPattern(
        weekdays=frozenset({0, 1, 2, 3, 4}), start=time(9, 0), end=time(15, 0),
        basis=FactOrigin.OBSERVED))
    fam = _family([andy, ali])
    assert fam.shared_windows(["Andy", "Ali"], MONDAY, MONDAY, min_hours=1.0) == []


def test_no_together_window_when_only_a_parent_could_cover():
    # Weekend, no school, no other caregiver → for both to be out, nobody's
    # left with Stevie. No together window (a parent covering isn't "together").
    andy = Caregiver(name="Andy", role="PARENT")
    ali = Caregiver(name="Ali", role="PARENT")
    fam = _family([andy, ali], school=False)
    saturday = date(2026, 9, 19)
    assert fam.shared_windows(["Andy", "Ali"], saturday, saturday) == []


def test_a_grandparent_staying_home_opens_a_together_window():
    # No school (weekend) but a relative caregiver is free to hold Stevie.
    andy = Caregiver(name="Andy", role="PARENT")
    ali = Caregiver(name="Ali", role="PARENT")
    grandma = Caregiver(name="Grandma", role="RELATIVE")  # free all day
    fam = _family([andy, ali, grandma], school=False)
    saturday = date(2026, 9, 19)
    windows = fam.shared_windows(["Andy", "Ali"], saturday, saturday, min_hours=1.0)
    assert windows, "grandma covering should free both parents"
    assert any("Grandma" in label for label in windows[0].child_covered_by)


def test_every_child_must_be_covered_for_together_time():
    caregivers = [Caregiver(name="Andy", role="PARENT"),
                  Caregiver(name="Ali", role="PARENT")]
    schooled = CoverageEngine(CareRecipient("Stevie", time(8, 0), time(18, 0)),
                              caregivers, school=_school(), now=NOW)
    # A toddler with no school and no non-parent coverage.
    toddler = CoverageEngine(CareRecipient("Nora", time(8, 0), time(18, 0)),
                             caregivers, now=NOW)
    fam = FamilyCoverage([schooled, toddler])
    # Stevie's at school, but Nora has nobody but the parents → no together time.
    assert fam.shared_windows(["Andy", "Ali"], MONDAY, MONDAY) == []


def test_shared_windows_rejects_unknown_caregiver():
    import pytest
    fam = _family([Caregiver(name="Andy", role="PARENT")])
    with pytest.raises(KeyError):
        fam.shared_windows(["Andy", "Ghost"], MONDAY, MONDAY)


# --- through the briefing --------------------------------------------------------
def _two_parent_household(fam: str) -> None:
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{
            "recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                          "supervised_end": "18:00:00"},
            "school": {"name": "ISLA", "first_day": "2020-01-01",
                       "last_day": "2030-12-31", "school_start": "09:00:00",
                       "school_end": "15:00:00"},
        }],
        "caregivers": [{"name": "Andy", "role": "PARENT"},
                       {"name": "Ali", "role": "PARENT"}],
    })


def test_together_intention_routes_to_together_windows():
    fam = "fam_together_route"
    _two_parent_household(fam)
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Yoga at Lifetime", "type": "standing",
                      "context": "together"})
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Solo lift", "type": "standing",
                      "context": "alone"})

    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["together"] == 1
    assert block["counts"]["alone"] == 1
    assert [i["description"] for i in block["together_intentions"]] == ["Yoga at Lifetime"]
    assert [i["description"] for i in block["alone_intentions"]] == ["Solo lift"]
    # Both-parents-free windows exist (school-covered weekday hours).
    assert block["counts"]["together_windows"] >= 1


def test_context_defaults_to_alone_and_validates():
    fam = "fam_ctx_default"
    r = client.post(f"/v1/families/{fam}/intentions", json={"description": "Gym"})
    assert r.json()["context"] == "alone"
    assert client.post(f"/v1/families/{fam}/intentions",
                       json={"description": "x", "context": "orgy"}).status_code == 400


def test_single_parent_household_has_no_together_windows():
    fam = "fam_single_parent"
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{"recipient": {"name": "Stevie"}}],
        "caregivers": [{"name": "Andy", "role": "PARENT"}],
    })
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "date night", "context": "together"})
    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["together_windows"] == 0
    # The intention still surfaces (UI shows "connect both calendars").
    assert block["counts"]["together"] == 1
