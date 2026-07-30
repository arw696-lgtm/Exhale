"""The Weekly Reflection — Exhale's Sunday exhale.

Holds the reflection to the product's honesty rail: it reflects only what
actually happened. A full week earns a lift, a hard week is named as hard, a
quiet week stays quiet — and a window you set but missed is never counted as a
win.
"""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.graph import KnowledgeGraph, Node, NodeType
from exhale.reflection import build_weekly_reflection

client = TestClient(app)


def _graph_with_events(*events):
    """A graph carrying EVENT nodes: each arg is (name, date)."""

    g = KnowledgeGraph()
    for i, (name, when) in enumerate(events):
        g.add_node(Node(
            node_id=f"event_{i}", type=NodeType.EVENT,
            properties={"name": name, "event_date": when.isoformat()},
        ))
    return g

NOW = datetime(2026, 7, 26, 18, 0)  # a Sunday evening


def _resolved(item_id, text, *, days_ago, kind="dependency_gap"):
    return {
        "item_id": item_id, "resolved_type": kind, "brief_description": text,
        "resolved_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def _intention(desc, *, matched_days_ago=None, outcome=None, status="open",
               surfaced=0, iid="int_x", context="alone"):
    return {
        "intention_id": iid, "description": desc, "context": context,
        "type": "one_off", "status": status, "surfaced_count": surfaced,
        "matched_at": (NOW - timedelta(days=matched_days_ago)).isoformat()
        if matched_days_ago is not None else None,
        "follow_up_outcome": outcome,
    }


def _wait(who, about, *, days_ago, wid="wait_x", resolved=False):
    return {
        "id": wid, "who": who, "about": about,
        "since": (NOW.date() - timedelta(days=days_ago)).isoformat(),
        "resolved": resolved, "resolved_at": None,
    }


# --- quiet / empty ----------------------------------------------------------------
def test_empty_week_is_honestly_quiet():
    r = build_weekly_reflection({}, None, now=NOW)
    assert r["view"] == "weekly_reflection"
    assert r["tenor"]["key"] == "quiet"
    assert r["carried"] == {"count": 0, "items": [], "by_person": [],
                            "hard_won": [], "events": []}
    assert r["lingering"] == {"count": 0, "items": []}


# --- what you carried -------------------------------------------------------------
def test_carried_holds_recent_resolutions_only():
    profile = {"resolved_log": [
        _resolved("g1", "Camp registration — handled", days_ago=2),
        _resolved("g2", "Ancient history", days_ago=10),  # outside the 7-day window
    ]}
    carried = build_weekly_reflection(profile, None, now=NOW)["carried"]
    assert carried["count"] == 1
    assert carried["items"][0]["text"] == "Camp registration — handled"


def test_honored_intention_counts_missed_one_does_not():
    profile = {"intentions": [
        _intention("Guitar practice", matched_days_ago=3, outcome="happened", iid="a"),
        _intention("Long run", matched_days_ago=3, outcome="didnt_happen", iid="b"),
        _intention("Coffee with Sam", matched_days_ago=3, outcome=None, iid="c"),
    ]}
    carried = build_weekly_reflection(profile, None, now=NOW)["carried"]
    texts = [i["text"] for i in carried["items"]]
    assert "Guitar practice" in texts        # confirmed happened
    assert "Coffee with Sam" in texts        # matched, follow-up not yet answered
    assert "Long run" not in texts           # set a window, missed it — not a win


def test_hard_won_surfaces_long_wanted_things():
    profile = {"intentions": [
        _intention("Finally read at night", matched_days_ago=1, outcome="happened",
                   surfaced=4, iid="hw"),
        _intention("Quick call", matched_days_ago=1, outcome="happened",
                   surfaced=0, iid="routine"),
    ]}
    hard = build_weekly_reflection(profile, None, now=NOW)["carried"]["hard_won"]
    assert [h["text"] for h in hard] == ["Finally read at night"]


# --- what's still waiting ---------------------------------------------------------
def test_lingering_surfaces_stale_waits_with_a_nudge():
    profile = {"waiting_on": [
        _wait("Hennepin County", "arborist follow-up", days_ago=20, wid="dying"),
        _wait("Dentist", "reschedule cleaning", days_ago=8, wid="stale"),
        _wait("Coach", "carpool", days_ago=2, wid="fresh"),          # too fresh
        _wait("Old", "done thing", days_ago=30, wid="closed", resolved=True),
    ]}
    ling = build_weekly_reflection(profile, None, now=NOW)["lingering"]
    ids = [i["id"] for i in ling["items"]]
    assert ids == ["dying", "stale"]                 # fresh + resolved excluded
    assert ling["items"][0]["dying"] is True         # 20 days → thread is dying
    assert all(i["action"] == "nudge" for i in ling["items"])


def test_lingering_offers_to_schedule_long_running_wants():
    profile = {"intentions": [
        _intention("Plan the garden", status="open", surfaced=4, iid="want"),
        _intention("Passing thought", status="open", surfaced=1, iid="whim"),
    ]}
    ling = build_weekly_reflection(profile, None, now=NOW)["lingering"]
    assert [i["id"] for i in ling["items"]] == ["want"]   # only the persistent one
    assert ling["items"][0]["action"] == "schedule"
    assert ling["items"][0]["suggestion"] == "Make time this week"


def test_dying_threads_sort_ahead_of_schedulable_wants():
    profile = {
        "waiting_on": [_wait("County", "follow-up", days_ago=20, wid="w")],
        "intentions": [_intention("A want", status="stale", surfaced=5, iid="i")],
    }
    ling = build_weekly_reflection(profile, None, now=NOW)["lingering"]
    assert [i["kind"] for i in ling["items"]] == ["waiting", "intention"]


# --- seen by name: who carried what -----------------------------------------------
def _resolved_by(item_id, text, by, *, days_ago=1, kind="task"):
    return {**_resolved(item_id, text, days_ago=days_ago, kind=kind), "by": by}


def test_carried_groups_by_person_names_never_numbers():
    profile = {"resolved_log": [
        _resolved_by("t1", "Mowed the lawn — done by Andy", "Andy"),
        _resolved_by("t2", "Called the plumber — done by Ali", "Ali"),
        _resolved_by("t3", "Camp form — handled", None, kind="dependency_gap"),
    ]}
    groups = build_weekly_reflection(profile, None, now=NOW)["carried"]["by_person"]
    names = [g["name"] for g in groups]
    assert names == ["Ali", "Andy", None]  # alphabetical, household last
    for g in groups:
        assert set(g) == {"name", "items"}  # no counts/totals — nothing to score with


def test_no_zero_sections_for_a_quiet_member():
    # Only Ali did logged things this week — Andy gets no group, not an empty one.
    profile = {"resolved_log": [
        _resolved_by("t1", "Called the plumber — done by Ali", "Ali"),
    ]}
    groups = build_weekly_reflection(profile, None, now=NOW)["carried"]["by_person"]
    assert [g["name"] for g in groups] == ["Ali"]


def test_together_intention_groups_as_together_not_a_person():
    profile = {"intentions": [{
        "intention_id": "int_t", "description": "Date night", "context": "together",
        "type": "one_off", "status": "matched", "surfaced_count": 0,
        "created_by": "Andy",
        "matched_at": (NOW - timedelta(days=2)).isoformat(),
        "follow_up_outcome": "happened",
    }]}
    groups = build_weekly_reflection(profile, None, now=NOW)["carried"]["by_person"]
    assert groups[0]["name"] == "Together"  # shared wins lead; no one owns them


def test_personal_intention_credits_its_creator():
    profile = {"intentions": [{
        "intention_id": "int_p", "description": "Long run", "context": "alone",
        "type": "one_off", "status": "matched", "surfaced_count": 0,
        "created_by": "Ali",
        "matched_at": (NOW - timedelta(days=2)).isoformat(),
        "follow_up_outcome": "happened",
    }]}
    groups = build_weekly_reflection(profile, None, now=NOW)["carried"]["by_person"]
    assert [g["name"] for g in groups] == ["Ali"]


def test_ordering_is_never_by_volume():
    # Andy did 3 things, Ali 1 — Ali still comes first (alphabetical, not ranked).
    profile = {"resolved_log": [
        _resolved_by("a1", "thing 1 — done by Andy", "Andy"),
        _resolved_by("a2", "thing 2 — done by Andy", "Andy"),
        _resolved_by("a3", "thing 3 — done by Andy", "Andy"),
        _resolved_by("b1", "thing 4 — done by Ali", "Ali"),
    ]}
    groups = build_weekly_reflection(profile, None, now=NOW)["carried"]["by_person"]
    assert [g["name"] for g in groups] == ["Ali", "Andy"]


# --- the lived week (calendar events) ---------------------------------------------
def test_carried_pulls_past_calendar_events():
    graph = _graph_with_events(
        ("Bachman's garden center", NOW.date() - timedelta(days=1)),   # this week, past
        ("Soccer game", NOW.date() - timedelta(days=3)),               # this week, past
        ("Dentist next month", NOW.date() + timedelta(days=20)),       # future — a plan
        ("Old thing", NOW.date() - timedelta(days=15)),                # before the window
    )
    events = build_weekly_reflection({}, None, graph=graph, now=NOW)["carried"]["events"]
    names = [e["name"] for e in events]
    assert names == ["Bachman's garden center", "Soccer game"]  # newest first, past-only


def test_events_do_not_inflate_the_tenor():
    # A week where nothing was accomplished but the calendar was full stays honest.
    graph = _graph_with_events(*[(f"Outing {i}", NOW.date() - timedelta(days=i + 1))
                                 for i in range(5)])
    r = build_weekly_reflection({}, None, graph=graph, now=NOW)
    assert r["carried"]["count"] == 0        # events aren't accomplishments
    assert len(r["carried"]["events"]) == 5
    assert r["tenor"]["key"] == "quiet"      # not falsely "full"


def test_event_is_not_duplicated_when_its_task_was_cleared():
    profile = {"resolved_log": [
        _resolved("g1", "Field trip permission slip — signed & sent", days_ago=2)]}
    graph = _graph_with_events(("Field trip", NOW.date() - timedelta(days=1)))
    events = build_weekly_reflection(profile, None, graph=graph, now=NOW)["carried"]["events"]
    assert events == []  # "Field trip" already lives in the cleared-task text


def test_no_graph_means_no_events_key_payload():
    carried = build_weekly_reflection({}, None, now=NOW)["carried"]
    assert carried["events"] == []


# --- tenor: the honest read over the top ------------------------------------------
def test_full_week_earns_a_lift():
    profile = {"resolved_log": [
        _resolved(f"g{i}", f"thing {i}", days_ago=1) for i in range(3)]}
    tenor = build_weekly_reflection(profile, None, now=NOW)["tenor"]
    assert tenor["key"] == "full"
    assert "did a lot" in tenor["headline"].lower()


def test_hard_week_is_named_hard_not_celebrated():
    # Nothing resolved, but real pressure open (stale wait + a critical care gap).
    profile = {"waiting_on": [_wait("County", "arborist", days_ago=20)]}
    care_watch = {"summary": {"critical": 2, "important": 1}}
    tenor = build_weekly_reflection(profile, care_watch, now=NOW)["tenor"]
    assert tenor["key"] == "hard"
    assert "hard one" in tenor["headline"].lower()
    assert "party" not in tenor["subhead"].lower()  # never confetti on a hard week


def test_mixed_week_shows_both_sides():
    profile = {
        "resolved_log": [_resolved("g1", "one win", days_ago=1)],
        "waiting_on": [
            _wait("A", "x", days_ago=20, wid="a"),
            _wait("B", "y", days_ago=18, wid="b"),
        ],
    }
    tenor = build_weekly_reflection(profile, None, now=NOW)["tenor"]
    assert tenor["key"] == "mixed"


def test_steady_week_is_understated():
    profile = {"resolved_log": [_resolved("g1", "one thing", days_ago=1)]}
    tenor = build_weekly_reflection(profile, None, now=NOW)["tenor"]
    assert tenor["key"] == "steady"


# --- API --------------------------------------------------------------------------
def test_reflection_endpoint_cold_family_is_quiet():
    r = client.get("/v1/families/fam_reflect_cold/reflection").json()
    assert r["view"] == "weekly_reflection"
    assert r["tenor"]["key"] == "quiet"


def test_reflection_endpoint_reflects_a_resolved_catch():
    fam = "fam_reflect_live"
    # Commit an obligation, then approve it — a real resolution flows to the log.
    soon = date.today() + timedelta(days=5)
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Field trip form", "target_person_name": "Stevie",
        "event_date": (soon + timedelta(days=10)).isoformat(),
        "deadline_date": soon.isoformat(),
        "action_required": True, "confidence_score": 0.97,
    })
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    ob = next(e["obligation_node_id"] for e in ledger if e["obligation_node_id"])
    client.post(f"/v1/families/{fam}/actions/approve", json={"obligation_node_id": ob})

    r = client.get(f"/v1/families/{fam}/reflection").json()
    assert r["carried"]["count"] == 1
    assert "Field trip form" in r["carried"]["items"][0]["text"]
