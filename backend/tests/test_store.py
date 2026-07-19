"""Tests for the HouseholdStore ingestion + routing integration (§3.3, §7)."""

from datetime import date, timedelta

from exhale.graph import NodeType
from exhale.schemas import ExtractionPayload
from exhale.store import HouseholdStore


def _payload(score: float, *, deadline=None, action=True) -> ExtractionPayload:
    return ExtractionPayload(
        extracted_event="Field Trip Permission Slip",
        target_person_name="Olivia",
        event_date=date(2026, 8, 25),
        deadline_date=deadline,
        action_required=action,
        confidence_score=score,
    )


def test_high_confidence_commits_obligation_to_graph():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(0.97, deadline=date(2026, 8, 20)))
    assert entry.decision.status.value == "COMMITTED"
    assert entry.obligation_node_id is not None
    graph = store.graph("fam1")
    obligations = [n for n in graph.nodes.values() if n.type is NodeType.OBLIGATION]
    assert len(obligations) == 1
    events = [n for n in graph.nodes.values() if n.type is NodeType.EVENT]
    assert len(events) == 1  # anchor auto-created


def test_medium_confidence_does_not_touch_graph():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(0.80))
    assert entry.decision.status.value == "PENDING_VERIFICATION"
    assert entry.obligation_node_id is None
    assert store.graph("fam1").nodes == {}


def test_low_confidence_rejected():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(0.40))
    assert entry.decision.status.value == "REJECTED"
    assert store.graph("fam1").nodes == {}


def test_anchor_event_is_reused_across_extractions():
    store = HouseholdStore()
    store.ingest("fam1", _payload(0.95, deadline=date(2026, 8, 20)))
    store.ingest("fam1", _payload(0.95, deadline=date(2026, 8, 21)))
    graph = store.graph("fam1")
    events = [n for n in graph.nodes.values() if n.type is NodeType.EVENT]
    obligations = [n for n in graph.nodes.values() if n.type is NodeType.OBLIGATION]
    assert len(events) == 1  # same event name reused
    assert len(obligations) == 2


def test_ledger_records_every_ingestion():
    store = HouseholdStore()
    store.ingest("fam1", _payload(0.97, deadline=date(2026, 8, 20)))
    store.ingest("fam1", _payload(0.50))
    ledger = store.ledger("fam1")
    assert len(ledger) == 2
    assert {e.decision.status.value for e in ledger} == {"COMMITTED", "REJECTED"}


def test_families_are_isolated():
    store = HouseholdStore()
    store.ingest("fam1", _payload(0.97, deadline=date(2026, 8, 20)))
    assert store.graph("fam2").nodes == {}
