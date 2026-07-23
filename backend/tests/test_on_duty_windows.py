"""On-duty windows: you've got the kid, but you're not slammed.

The third kind of time — the exact complement of a work window. Not free-and-
covered, not a gap: you're home with the child, uncommitted, and it's a fine
stretch for the things that don't need the kid gone (email the teacher, tidy).
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
NOW = datetime(2026, 9, 13, 20, 0)


def _school():
    return SchoolCalendar(name="ISLA", first_day=date(2026, 9, 1),
                          last_day=date(2027, 6, 3),
                          school_start=time(9, 0), school_end=time(15, 0))


def test_on_duty_is_the_bookends_around_school():
    # Andy home all day, Stevie supervised 8–18, school 9–15, no one else.
    andy = Caregiver(name="Andy", role="PARENT")
    fam = FamilyCoverage([CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), [andy],
        school=_school(), now=NOW)])
    on_duty = fam.on_duty_windows("Andy", MONDAY, MONDAY, min_hours=0.5)
    spans = {(w.start.time(), w.end.time()) for w in on_duty}
    # Before school (8–9) and after (15–18): Andy has Stevie, uncommitted.
    assert spans == {(time(8, 0), time(9, 0)), (time(15, 0), time(18, 0))}
    assert all("Stevie" in " ".join(w.child_covered_by) for w in on_duty)


def test_on_duty_and_work_window_are_complementary():
    # School 9–15 is a work window (Stevie covered); the rest of Andy's free
    # day is on-duty. The two must not overlap and must tile his free time.
    andy = Caregiver(name="Andy", role="PARENT")
    fam = FamilyCoverage([CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), [andy],
        school=_school(), now=NOW)])
    work = fam.work_windows("Andy", MONDAY, MONDAY, min_hours=0.5)
    on_duty = fam.on_duty_windows("Andy", MONDAY, MONDAY, min_hours=0.5)
    assert {(w.start.time(), w.end.time()) for w in work} == {(time(9, 0), time(15, 0))}
    # No overlap between the two window kinds.
    for a in work:
        for b in on_duty:
            assert not (a.start < b.end and b.start < a.end)


def test_solo_parenting_day_is_all_on_duty():
    # Weekend, no school; Andy home, no other coverage → he's on all day.
    andy = Caregiver(name="Andy", role="PARENT")
    fam = FamilyCoverage([CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), [andy], now=NOW)])
    saturday = date(2026, 9, 19)
    (w,) = fam.on_duty_windows("Andy", saturday, saturday, min_hours=0.5)
    assert w.start.time() == time(8, 0) and w.end.time() == time(18, 0)


def test_working_hours_are_not_on_duty():
    # Andy works 9–17 → not free, so not on-duty; only the free bookends are.
    andy = Caregiver(name="Andy", role="PARENT", work_pattern=WorkPattern(
        weekdays=frozenset({0, 1, 2, 3, 4}), start=time(9, 0), end=time(17, 0),
        basis=FactOrigin.OBSERVED))
    fam = FamilyCoverage([CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), [andy], now=NOW)])
    on_duty = fam.on_duty_windows("Andy", MONDAY, MONDAY, min_hours=0.25)
    for w in on_duty:
        assert not (w.start.time() >= time(9, 0) and w.end.time() <= time(17, 0))
    spans = {(w.start.time(), w.end.time()) for w in on_duty}
    assert spans == {(time(8, 0), time(9, 0)), (time(17, 0), time(18, 0))}


def test_unknown_caregiver_raises():
    import pytest
    fam = FamilyCoverage([CoverageEngine(
        CareRecipient("Stevie"), [Caregiver(name="Andy")], now=NOW)])
    with pytest.raises(KeyError):
        fam.on_duty_windows("Ghost", MONDAY, MONDAY)


# --- through the briefing --------------------------------------------------------
def test_on_duty_intention_routes_to_on_duty_windows():
    fam = "fam_on_duty_route"
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{
            "recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                          "supervised_end": "18:00:00"},
            "school": {"name": "ISLA", "first_day": "2020-01-01",
                       "last_day": "2030-12-31", "school_start": "09:00:00",
                       "school_end": "15:00:00"},
        }],
        "caregivers": [{"name": "Andy", "role": "PARENT"}],
    })
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Email Stevie's teacher", "context": "on_duty"})
    client.post(f"/v1/families/{fam}/intentions",
                json={"description": "Solo lift", "context": "alone"})

    block = client.get(f"/v1/families/{fam}/briefing").json()["time_for_what_matters"]
    assert block["counts"]["on_duty"] == 1
    assert block["counts"]["alone"] == 1
    assert [i["description"] for i in block["on_duty_intentions"]] == ["Email Stevie's teacher"]
    # A home parent with a schooled kid has real on-duty bookends.
    assert block["counts"]["on_duty_windows"] >= 1


def test_context_on_duty_validates():
    fam = "fam_on_duty_valid"
    r = client.post(f"/v1/families/{fam}/intentions",
                    json={"description": "clean bathrooms", "context": "on_duty"})
    assert r.status_code == 200 and r.json()["context"] == "on_duty"
    assert client.post(f"/v1/families/{fam}/intentions",
                       json={"description": "x", "context": "whenever"}).status_code == 400
