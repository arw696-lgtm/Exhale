"""Multi-child coverage: FamilyCoverage math, wire normalization, API behavior.

The household reality check: families have one, two, or five kids. Gaps are
per-child facts (merge); work windows require EVERY child covered (intersect).
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
    build_family_care_watch,
)
from exhale.coverage_config import CoverageModelIn, build_engines, build_family
from exhale.schemas import FactOrigin

client = TestClient(app)

# A school week: Mon 2026-09-14 .. Fri 2026-09-18.
MONDAY = date(2026, 9, 14)
NOW = datetime(2026, 9, 13, 20, 0)


def _caregivers():
    """Two working parents, both out 09:00–15:00 every weekday."""

    pattern = WorkPattern(weekdays=frozenset({0, 1, 2, 3, 4}),
                          start=time(9, 0), end=time(15, 0),
                          basis=FactOrigin.OBSERVED)
    return [Caregiver(name="Andy", work_pattern=pattern),
            Caregiver(name="Ali", work_pattern=WorkPattern(
                weekdays=frozenset({0, 1, 2, 3, 4}),
                start=time(9, 0), end=time(15, 0), basis=FactOrigin.OBSERVED))]


def _school(name="ISLA", start=time(9, 0), end=time(15, 0)):
    return SchoolCalendar(name=name, first_day=date(2026, 9, 1),
                          last_day=date(2027, 6, 3),
                          school_start=start, school_end=end)


def test_gaps_merge_per_child():
    """School covers the older kid; the toddler is uncovered while both work."""

    caregivers = _caregivers()
    schooled = CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), caregivers,
        school=_school(), now=NOW)
    toddler = CoverageEngine(
        CareRecipient("Nora", time(8, 0), time(18, 0)), caregivers, now=NOW)
    family = FamilyCoverage([schooled, toddler])

    gaps = family.scan_range(MONDAY, MONDAY)
    by_child = {}
    for g in gaps:
        by_child.setdefault(g.recipient_name, []).append(g)
    # Stevie: school 9–3 covers exactly the parents' work block — no gap.
    assert "Stevie" not in by_child
    # Nora: uncovered 9–3 while both parents work.
    (nora_gap,) = by_child["Nora"]
    assert nora_gap.start.time() == time(9, 0)
    assert nora_gap.end.time() == time(15, 0)


def test_work_windows_require_every_child_covered():
    """One kid at school does NOT free a parent whose toddler is home."""

    caregivers = _caregivers()
    schooled = CoverageEngine(
        CareRecipient("Stevie", time(8, 0), time(18, 0)), caregivers,
        school=_school(), now=NOW)
    toddler = CoverageEngine(
        CareRecipient("Nora", time(8, 0), time(18, 0)), caregivers, now=NOW)

    # Alone, Stevie's school 9–3 would give Andy a 9–3 window... but Andy works
    # 9–3 himself here, so give Andy no work pattern to isolate the math.
    free_andy = Caregiver(name="Andy")
    ali = caregivers[1]
    schooled_f = CoverageEngine(CareRecipient("Stevie", time(8, 0), time(18, 0)),
                                [free_andy, ali], school=_school(), now=NOW)
    toddler_f = CoverageEngine(CareRecipient("Nora", time(8, 0), time(18, 0)),
                               [free_andy, ali], now=NOW)

    solo = schooled_f.work_windows("Andy", MONDAY, MONDAY, min_hours=0.5)
    assert solo, "single-child sanity: school frees Andy"

    family = FamilyCoverage([schooled_f, toddler_f])
    windows = family.work_windows("Andy", MONDAY, MONDAY, min_hours=0.5)
    # Ali works 9–3 (can't take Nora); school only has Stevie. With Nora
    # uncovered 9–3, Andy's schooled-child window must NOT survive as 9–3.
    # Ali is free 8–9 and 15–18 → those stretches cover BOTH kids only outside
    # school hours for Stevie... Stevie is covered by Ali too when Ali is free.
    for w in windows:
        assert not (w.start.time() >= time(9, 0) and w.end.time() <= time(15, 0)), (
            f"window {w.start}–{w.end} exists while the toddler is uncovered")
    # The surviving windows are exactly when Ali (free) has both kids: 8–9, 15–18.
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert spans == {(time(8, 0), time(9, 0)), (time(15, 0), time(18, 0))}


def test_family_care_watch_names_children():
    caregivers = [Caregiver(name="Andy", work_pattern=WorkPattern(
        weekdays=frozenset({0}), start=time(9, 0), end=time(12, 0),
        basis=FactOrigin.INFERRED))]
    a = CoverageEngine(CareRecipient("Stevie", time(9, 0), time(12, 0)),
                       caregivers, now=NOW)
    b = CoverageEngine(CareRecipient("Nora", time(9, 0), time(12, 0)),
                       caregivers, now=NOW)
    watch = build_family_care_watch(FamilyCoverage([a, b]), MONDAY, MONDAY)
    assert watch["recipient"] == "Stevie & Nora"
    assert watch["recipients"] == ["Stevie", "Nora"]
    assert watch["summary"]["total_gaps"] == 2
    assert {g["recipient"] for g in watch["gaps"]} == {"Stevie", "Nora"}


# --- wire format ----------------------------------------------------------------
def test_legacy_single_child_model_normalizes():
    model = CoverageModelIn(**{
        "recipient": {"name": "Stevie"},
        "caregivers": [{"name": "Andy"}],
        "school": {"name": "ISLA", "first_day": "2026-09-01", "last_day": "2027-06-03"},
    })
    assert len(model.children) == 1
    assert model.children[0].recipient.name == "Stevie"
    assert model.children[0].school.name == "ISLA"
    assert model.recipient is None and model.school is None  # canonicalized

    # Round-trips through dump/parse (the stored-profile path).
    again = CoverageModelIn(**model.model_dump(mode="json"))
    assert [c.recipient.name for c in again.children] == ["Stevie"]

    # And builds one engine per child.
    engines = build_engines(model)
    assert [e.recipient.name for e in engines] == ["Stevie"]
    assert engines[0].school.name == "ISLA"


def test_children_model_builds_family():
    model = CoverageModelIn(**{
        "children": [
            {"recipient": {"name": "Stevie"},
             "school": {"name": "ISLA", "first_day": "2026-09-01",
                        "last_day": "2027-06-03"}},
            {"recipient": {"name": "Nora"}},
        ],
        "caregivers": [{"name": "Andy"}],
    })
    family = build_family(model)
    assert family.recipient_names == ["Stevie", "Nora"]


def test_model_without_any_child_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        CoverageModelIn(**{"caregivers": [{"name": "Andy"}]})


# --- API ------------------------------------------------------------------------
def test_api_multi_child_roundtrip_and_care_gaps():
    fam = "fam_multi_child"
    r = client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [
            {"recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                           "supervised_end": "18:00:00"},
             "school": {"name": "ISLA", "first_day": "2026-09-01",
                        "last_day": "2027-06-03", "school_start": "09:00:00",
                        "school_end": "15:00:00"}},
            {"recipient": {"name": "Nora", "supervised_start": "08:00:00",
                           "supervised_end": "18:00:00"}},
        ],
        "caregivers": [
            {"name": "Andy", "work_pattern": {"weekdays": [0, 1, 2, 3, 4],
                                              "start": "09:00:00", "end": "15:00:00",
                                              "basis": "OBSERVED"}},
        ],
    })
    body = r.json()
    assert body["children"] == ["Stevie", "Nora"]
    assert body["schools"] == {"Stevie": "ISLA"}

    watch = client.get(f"/v1/families/{fam}/care-gaps",
                       params={"from": "2026-09-14", "to": "2026-09-14"}).json()
    assert watch["recipients"] == ["Stevie", "Nora"]
    # Stevie is school-covered while Andy works; Nora is not.
    assert {g["recipient"] for g in watch["gaps"]} == {"Nora"}


def test_api_legacy_single_child_put_still_works():
    fam = "fam_legacy_child"
    r = client.put(f"/v1/families/{fam}/coverage-model", json={
        "recipient": {"name": "Solo"},
        "caregivers": [{"name": "Andy"}],
    })
    assert r.status_code == 200
    assert r.json()["children"] == ["Solo"]
    watch = client.get(f"/v1/families/{fam}/care-gaps").json()
    assert watch["recipient"] == "Solo"
    assert watch["recipients"] == ["Solo"]
