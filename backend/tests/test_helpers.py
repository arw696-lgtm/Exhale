"""Tests for the scoped-caregiver visibility core (helpers.py, FAMILY_STRUCTURES §3.2)."""

from dataclasses import dataclass

from exhale.helpers import (
    HelperScope,
    build_helper_view,
    filter_care_watch,
    helper_scope,
    set_helper_scope,
    shared_obligations,
)


# --- fakes --------------------------------------------------------------------
@dataclass
class _Node:
    properties: dict


class _Graph:
    def __init__(self, nodes: dict):
        self.nodes = nodes


def _gap(date_iso: str, band="CRITICAL", inferred=False) -> dict:
    return {"date": date_iso, "start": f"{date_iso}T09:00:00",
            "end": f"{date_iso}T12:00:00", "threat_level": band,
            "depends_on_inference": inferred, "reason": "school closed"}


# 2026-09-01 is a Tuesday; 09-02 Wed; 09-03 Thu; 09-04 Fri; 09-05 Sat.
CARE_WATCH = {
    "recipient": "Stevie",
    "gaps": [_gap("2026-09-01"), _gap("2026-09-02", "IMPORTANT"),
             _gap("2026-09-03", "ADVISORY", inferred=True), _gap("2026-09-04")],
}


# --- scope --------------------------------------------------------------------
def test_scope_covers_weekday():
    scope = HelperScope(weekdays=frozenset({1, 3}), shared_obligation_ids=frozenset())
    from datetime import date
    assert scope.covers(date(2026, 9, 1))   # Tuesday
    assert scope.covers(date(2026, 9, 3))   # Thursday
    assert not scope.covers(date(2026, 9, 2))  # Wednesday


def test_helper_scope_missing_defaults_empty():
    scope = helper_scope({}, "user_x")
    assert scope.weekdays == frozenset()
    assert scope.shared_obligation_ids == frozenset()


def test_helper_scope_reads_profile():
    profile = {"helpers": {"u1": {"weekdays": [1, 3], "shared_obligation_ids": ["ob_1"]}}}
    scope = helper_scope(profile, "u1")
    assert scope.weekdays == {1, 3}
    assert scope.shared_obligation_ids == {"ob_1"}


def test_set_helper_scope_merges_without_clobbering():
    helpers = {"u1": {"weekdays": [1], "shared_obligation_ids": ["ob_1"],
                      "display_name": "Grandma"}}
    # Editing weekdays leaves shares and display_name intact.
    after = set_helper_scope(helpers, "u1", weekdays=[1, 3])
    assert after["u1"]["weekdays"] == [1, 3]
    assert after["u1"]["shared_obligation_ids"] == ["ob_1"]
    assert after["u1"]["display_name"] == "Grandma"
    # Sharing an item leaves weekdays intact.
    after2 = set_helper_scope(after, "u1", shared_obligation_ids=["ob_1", "ob_2"])
    assert after2["u1"]["weekdays"] == [1, 3]
    assert after2["u1"]["shared_obligation_ids"] == ["ob_1", "ob_2"]


# --- care-watch filtering -----------------------------------------------------
def test_filter_care_watch_keeps_only_covered_days():
    scope = HelperScope(weekdays=frozenset({1, 3}), shared_obligation_ids=frozenset())
    view = filter_care_watch(CARE_WATCH, scope)
    dates = [g["date"] for g in view["gaps"]]
    assert dates == ["2026-09-01", "2026-09-03"]  # Tue + Thu only
    assert view["summary"]["total_gaps"] == 2
    assert view["summary"]["critical"] == 1        # Tue
    assert view["summary"]["advisory"] == 1        # Thu
    assert view["summary"]["important"] == 0       # Wed was dropped
    assert view["summary"]["assumption_dependent"] == 1  # Thu inferred
    assert view["covered_weekdays"] == ["Tuesday", "Thursday"]


def test_filter_care_watch_handles_no_model():
    scope = HelperScope(weekdays=frozenset({0}), shared_obligation_ids=frozenset())
    view = filter_care_watch(None, scope)
    assert view["gaps"] == []
    assert view["summary"]["total_gaps"] == 0


# --- shared obligations -------------------------------------------------------
def test_shared_obligations_are_minimal_and_provenance_free():
    graph = _Graph({
        "ob_1": _Node({"name": "Permission slip due", "target_person_name": "Stevie",
                       "deadline": "2026-09-01",
                       # provenance that MUST NOT leak to a helper:
                       "source_document_name": "Subject: forms from mom's inbox",
                       "source_reference": "gmail_msg_42"}),
    })
    scope = HelperScope(weekdays=frozenset(), shared_obligation_ids=frozenset({"ob_1"}))
    (item,) = shared_obligations(graph, scope)
    assert item == {"obligation_id": "ob_1", "title": "Permission slip due",
                    "person": "Stevie", "date": "2026-09-01"}
    assert "source_document_name" not in item
    assert "source_reference" not in item


def test_shared_obligations_skips_missing_ids():
    graph = _Graph({})
    scope = HelperScope(weekdays=frozenset(), shared_obligation_ids=frozenset({"gone"}))
    assert shared_obligations(graph, scope) == []


def test_build_helper_view_assembles_scope():
    graph = _Graph({"ob_1": _Node({"name": "Field trip", "event_date": "2026-09-03"})})
    profile = {"helpers": {"u1": {"weekdays": [1, 3], "shared_obligation_ids": ["ob_1"]}}}
    view = build_helper_view(profile, graph, CARE_WATCH, "u1")
    assert view["view"] == "helper_home"
    assert view["care_watch"]["summary"]["total_gaps"] == 2
    assert len(view["shared_obligations"]) == 1
    assert view["scope"]["covered_weekdays"] == ["Tuesday", "Thursday"]
    assert view["scope"]["shared_count"] == 1
