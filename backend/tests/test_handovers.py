"""Who has the child — the fact the engine could not previously hold.

Everything the coverage model stored was about when a caregiver is *busy*. So
the only way to answer "who has Stevie on Saturday" was to invert busyness, and
an empty weekend diary became sixteen hours of promised free time on a day the
child was home the whole time.

A handover is the positive statement. Two forms, because households run on a
rhythm but real life interrupts it: a standing arrangement ("Ali has Stevie
Tuesdays and Thursdays, 4pm to 8pm") and a one-off ("Grandma has him this
Saturday evening").

It buys three things, one per section below: windows that rest on something
real, gaps that a handover can close even when the holder's calendar looks
busy, and — only findable once handovers exist — the case where someone is
down to have the child and is also booked elsewhere.
"""

from datetime import date, datetime, time

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.coverage import (
    CareAssignment,
    CareRecipient,
    Caregiver,
    CoverageEngine,
    HandoverPattern,
    SchoolCalendar,
    WorkPattern,
)

client = TestClient(app)

STEVIE = CareRecipient("Stevie", time(6, 0), time(22, 0))
WEEKDAYS = frozenset({0, 1, 2, 3, 4})
SATURDAY = date(2026, 9, 19)
TUESDAY = date(2026, 9, 15)
NOW = datetime(2026, 9, 14, 6, 0)


def _andy(**kw):
    return Caregiver("Andy", "PARENT",
                     WorkPattern(WEEKDAYS, time(9, 0), time(17, 0)), **kw)


def _ali(**kw):
    return Caregiver("Ali", "PARENT",
                     WorkPattern(WEEKDAYS, time(9, 0), time(17, 0)), **kw)


def _engine(caregivers, school=None):
    return CoverageEngine(STEVIE, caregivers, school=school, now=NOW)


# --- windows rest on something stated ---------------------------------------------
def test_a_standing_arrangement_opens_a_window():
    ali = _ali(handover_patterns=[
        HandoverPattern(frozenset({1}), time(16, 0), time(20, 0), note="Ali has Stevie")
    ])
    windows = _engine([_andy(), ali]).open_windows_on(TUESDAY, "Andy")

    assert [(w.start.time(), w.end.time()) for w in windows] == [
        (time(17, 0), time(20, 0))  # Andy is at work until 5
    ]
    assert any("Ali" in label for label in windows[0].child_covered_by)


def test_a_standing_arrangement_only_applies_on_its_weekdays():
    ali = _ali(handover_patterns=[
        HandoverPattern(frozenset({1}), time(16, 0), time(20, 0))
    ])
    assert _engine([_andy(), ali]).open_windows_on(SATURDAY, "Andy") == []


def test_a_standing_arrangement_can_be_bounded():
    """An arrangement that ends does not have to be deleted to stop applying."""

    ali = _ali(handover_patterns=[
        HandoverPattern(frozenset({1}), time(16, 0), time(20, 0),
                        last_day=date(2026, 9, 8))
    ])
    assert _engine([_andy(), ali]).open_windows_on(TUESDAY, "Andy") == []


def test_a_one_off_covers_only_its_own_day():
    ali = _ali(care_assignments=[
        CareAssignment(datetime.combine(SATURDAY, time(17, 0)),
                       datetime.combine(SATURDAY, time(21, 0)))
    ])
    engine = _engine([_andy(), ali])

    assert [(w.start.time(), w.end.time())
            for w in engine.open_windows_on(SATURDAY, "Andy")] == [
        (time(17, 0), time(21, 0))
    ]
    assert engine.open_windows_on(TUESDAY, "Andy") == []


# --- handovers close gaps, and can never open one ---------------------------------
def test_a_handover_closes_a_gap_even_when_the_holder_looks_busy():
    """Coverage stated by a person outranks an inference about their diary."""

    school = SchoolCalendar(name="ISLA", first_day=date(2026, 9, 1),
                            last_day=date(2027, 6, 3))
    # Both parents at a concert Tuesday evening → normally a gap.
    concert = HandoverPattern(frozenset({1}), time(18, 0), time(21, 0))
    grandma = Caregiver("Grandma", "RELATIVE", handover_patterns=[concert])

    with_grandma = _engine([_andy(), _ali(), grandma], school=school)
    evening_gaps = [
        g for g in with_grandma.scan_day(TUESDAY)
        if g.start.time() >= time(18, 0) and g.end.time() <= time(21, 0)
    ]

    assert evening_gaps == []


def test_a_household_with_no_handovers_gains_no_new_gaps():
    """The safety property: handovers subtract from gaps, never add.

    Care gaps keep their permissive default on purpose — an alarm must never
    fire from not knowing. Adding the concept of a handover must not quietly
    turn every unstated hour into a gap.
    """

    school = SchoolCalendar(name="ISLA", first_day=date(2026, 9, 1),
                            last_day=date(2027, 6, 3))
    engine = _engine([_andy(), _ali()], school=school)

    assert engine.scan_day(SATURDAY) == []


# --- the thing only handovers can find --------------------------------------------
def test_a_handover_that_collides_with_the_holders_calendar_is_surfaced():
    """Worse than a gap, because nothing looks wrong until six o'clock."""

    from exhale.coverage import CalendarEvent

    ali = _ali(
        # 5pm start, so her ordinary working day is not itself the clash.
        handover_patterns=[HandoverPattern(frozenset({1}), time(17, 0), time(20, 0))],
        events=[CalendarEvent("Work dinner",
                              datetime.combine(TUESDAY, time(18, 0)),
                              datetime.combine(TUESDAY, time(21, 0)),
                              attendees=("Ali",))],
    )
    conflicts = _engine([_andy(), ali]).handover_conflicts_on(TUESDAY)

    assert len(conflicts) == 1
    assert conflicts[0]["caregiver"] == "Ali"
    assert conflicts[0]["recipient"] == "Stevie"
    assert "Work dinner" in conflicts[0]["clash"]
    # Only the overlapping stretch, not the whole handover.
    assert conflicts[0]["start"].endswith("18:00:00")
    assert conflicts[0]["end"].endswith("20:00:00")


def test_a_handover_that_starts_before_the_holder_stops_working_is_a_conflict():
    """The quiet version of the same fault, and the commonest in practice.

    Nothing exotic has to go wrong: Ali is down from 4 and works until 5. No
    gap is reported, because on paper she has him.
    """

    ali = _ali(handover_patterns=[
        HandoverPattern(frozenset({1}), time(16, 0), time(20, 0))
    ])
    conflicts = _engine([_andy(), ali]).handover_conflicts_on(TUESDAY)

    assert len(conflicts) == 1
    assert conflicts[0]["clash"] == "working"
    assert conflicts[0]["start"].endswith("16:00:00")
    assert conflicts[0]["end"].endswith("17:00:00")


def test_no_conflict_when_the_calendar_and_the_handover_agree():
    from exhale.coverage import CalendarEvent

    ali = _ali(
        handover_patterns=[HandoverPattern(frozenset({1}), time(17, 0), time(20, 0))],
        events=[CalendarEvent("Lunch", datetime.combine(TUESDAY, time(12, 0)),
                              datetime.combine(TUESDAY, time(13, 0)),
                              attendees=("Ali",))],
    )
    assert _engine([_andy(), ali]).handover_conflicts_on(TUESDAY) == []


def test_a_conflict_is_not_reported_as_a_gap():
    """The two say different things and must not be collapsed."""

    from exhale.coverage import CalendarEvent

    ali = _ali(
        handover_patterns=[HandoverPattern(frozenset({1}), time(17, 0), time(20, 0))],
        events=[CalendarEvent("Work dinner",
                              datetime.combine(TUESDAY, time(18, 0)),
                              datetime.combine(TUESDAY, time(21, 0)),
                              attendees=("Ali",))],
    )
    engine = _engine([_andy(), ali])

    assert engine.handover_conflicts_on(TUESDAY)
    assert not [g for g in engine.scan_day(TUESDAY)
                if g.start.time() >= time(18, 0) and g.end.time() <= time(20, 0)]


# --- through the API ---------------------------------------------------------------
def _household(fam):
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [{"recipient": {"name": "Stevie"}}],
        "caregivers": [{"name": "Andy", "role": "PARENT"},
                       {"name": "Ali", "role": "PARENT"}],
    })


def test_add_list_and_remove_a_recurring_handover():
    fam = "fam_handover_api"
    _household(fam)

    created = client.post(f"/v1/families/{fam}/handovers", json={
        "caregiver": "Ali", "weekdays": [1, 3],
        "start_time": "16:00:00", "end_time": "20:00:00",
        "note": "Ali has Stevie",
    })
    assert created.status_code == 200
    handover_id = created.json()["handover_id"]

    listed = client.get(f"/v1/families/{fam}/handovers").json()["handovers"]
    assert len(listed) == 1
    assert listed[0]["kind"] == "recurring"
    assert listed[0]["weekdays"] == [1, 3]
    assert listed[0]["caregiver"] == "Ali"

    assert client.delete(f"/v1/families/{fam}/handovers/{handover_id}").status_code == 200
    assert client.get(f"/v1/families/{fam}/handovers").json()["handovers"] == []


def test_add_a_one_off_handover():
    fam = "fam_handover_once"
    _household(fam)

    r = client.post(f"/v1/families/{fam}/handovers", json={
        "caregiver": "Ali",
        "start": "2026-09-19T17:00:00", "end": "2026-09-19T21:00:00",
    })

    assert r.status_code == 200
    assert r.json()["kind"] == "once"
    assert client.get(f"/v1/families/{fam}/handovers").json()["handovers"][0]["kind"] == "once"


def test_a_handover_for_someone_who_is_not_in_the_household_is_refused():
    fam = "fam_handover_unknown"
    _household(fam)

    r = client.post(f"/v1/families/{fam}/handovers", json={
        "caregiver": "Nobody", "weekdays": [1],
        "start_time": "16:00:00", "end_time": "20:00:00",
    })

    assert r.status_code == 400
    assert "Andy" in r.json()["detail"] and "Ali" in r.json()["detail"]


def test_an_incoherent_handover_is_refused():
    fam = "fam_handover_bad"
    _household(fam)

    backwards = client.post(f"/v1/families/{fam}/handovers", json={
        "caregiver": "Ali", "weekdays": [1],
        "start_time": "20:00:00", "end_time": "16:00:00",
    })
    assert backwards.status_code == 400

    neither = client.post(f"/v1/families/{fam}/handovers", json={"caregiver": "Ali"})
    assert neither.status_code == 400


def test_removing_a_handover_that_does_not_exist_is_a_404():
    fam = "fam_handover_missing"
    _household(fam)
    assert client.delete(f"/v1/families/{fam}/handovers/ho_nope").status_code == 404


def test_handovers_need_a_coverage_model():
    assert client.get("/v1/families/fam_no_model_here/handovers").status_code == 404
