"""Clearing retail notices that already reached the graph.

The load-bearing rules: it only ever closes things that still read as
commercial, it closes rather than deletes, and clearing junk is never
recorded as an accomplishment.
"""

from datetime import datetime, timedelta, timezone

from exhale.cleanup import NOT_RELEVANT, clear_committed_noise, find_committed_noise
from exhale.forgetting_engine import ForgettingEngine
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.store import HouseholdStore

NOW = datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc)
FAM = "fam_cleanup"


def _graph_with(*obligations):
    g = KnowledgeGraph()
    g.add_node(Node(node_id="anchor", type=NodeType.EVENT,
                    properties={"name": "This week", "event_date": "2026-09-20"}))
    for i, (node_id, name) in enumerate(obligations):
        g.add_node(Node(node_id=node_id, type=NodeType.OBLIGATION, properties={
            "name": name, "status": "UNRESOLVED",
            "deadline": (NOW + timedelta(days=2)).isoformat(),
            "likelihood_of_forgetting": 0.9, "impact_of_forgetting": 0.9,
        }))
        g.add_edge(Edge(edge_id=f"e{i}", type=EdgeType.DEPENDS_ON,
                        source_node_id="anchor", target_node_id=node_id))
    return g


def _seeded():
    store = HouseholdStore()
    store.set_graph(FAM, _graph_with(
        ("ob_order", "Your Drive Up order is ready at Bloomington 79th and Penn"),
        ("ob_stmt", "Your Statement is Ready"),
        ("ob_slip", "West High Field Trip Permission Slip"),
        ("ob_forms", "Request for Health Forms Return"),
    ))
    return store


# --- what it finds ----------------------------------------------------------
def test_finds_retail_leaves_real_obligations_alone():
    found = find_committed_noise(_seeded(), FAM)
    assert {i["obligation_node_id"] for i in found} == {"ob_order", "ob_stmt"}


def test_already_closed_items_are_not_offered_again():
    store = _seeded()
    clear_committed_noise(store, FAM, ["ob_order", "ob_stmt"])
    assert find_committed_noise(store, FAM) == []


# --- what clearing does -----------------------------------------------------
def test_cleared_items_stop_surfacing_as_gaps():
    store = _seeded()
    before = {g.obligation_node_id for g in
              ForgettingEngine(store.graph(FAM)).scan_all_anchors(now=NOW)}
    assert "ob_order" in before

    assert clear_committed_noise(store, FAM, ["ob_order", "ob_stmt"]) == 2
    after = {g.obligation_node_id for g in
             ForgettingEngine(store.graph(FAM)).scan_all_anchors(now=NOW)}
    assert "ob_order" not in after and "ob_stmt" not in after
    # The real ones are untouched.
    assert "ob_slip" in after and "ob_forms" in after


def test_closed_not_deleted_and_never_marked_done():
    """Nothing is erased, and NOT_RELEVANT is its own status — these were
    never completed, and clearing junk is not an accomplishment."""

    store = _seeded()
    clear_committed_noise(store, FAM, ["ob_order"])
    node = store.graph(FAM).nodes["ob_order"]
    assert node.properties["status"] == NOT_RELEVANT
    assert node.properties["status"] != "COMPLETED"
    # Every other property survived.
    assert node.properties["name"].startswith("Your Drive Up order")
    assert "deadline" in node.properties
    # And it left no trace in the week's wins.
    assert (store.profile(FAM).get("resolved_log") or []) == []


# --- what it refuses to do --------------------------------------------------
def test_a_real_obligation_is_refused_even_when_named():
    """A stale screen must not be able to close something real."""

    store = _seeded()
    assert clear_committed_noise(store, FAM, ["ob_slip", "ob_forms"]) == 0
    surviving = {g.obligation_node_id for g in
                 ForgettingEngine(store.graph(FAM)).scan_all_anchors(now=NOW)}
    assert {"ob_slip", "ob_forms"} <= surviving


def test_unknown_ids_are_skipped_not_fatal():
    store = _seeded()
    assert clear_committed_noise(store, FAM, ["nope", "ob_order"]) == 1


def test_empty_household_sweeps_cleanly():
    store = HouseholdStore()
    assert find_committed_noise(store, "fam_empty") == []
    assert clear_committed_noise(store, "fam_empty", ["anything"]) == 0
