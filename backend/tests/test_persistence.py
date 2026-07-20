"""Integration tests for the encrypted Postgres store (§5.3).

Require a running Postgres; skipped automatically when unreachable. CI provides
one via a service container; locally: EXHALE_TEST_DATABASE_URL or the default
postgres/postgres@localhost/exhale_test.
"""

import os
import uuid
from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get(
    "EXHALE_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/exhale_test",
)

try:
    with psycopg.connect(DSN, connect_timeout=3):
        _PG_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PG_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _PG_AVAILABLE, reason="Postgres not reachable")

from exhale.persistence import PersistentHouseholdStore  # noqa: E402
from exhale.schemas import ExtractionPayload  # noqa: E402

MASTER = "test-master-secret"


@pytest.fixture()
def family_id():
    return f"fam_{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def store():
    s = PersistentHouseholdStore(DSN, MASTER)
    yield s
    s.close()


def _payload(**over) -> ExtractionPayload:
    base = dict(
        extracted_event="Field Trip Permission Slip",
        target_person_name="Olivia",
        event_date=date(2026, 8, 25),
        deadline_date=date(2026, 8, 1),
        action_required=True,
        confidence_score=0.97,
        source_document_name="West High Newsletter",
        source_reference="msg_123",
    )
    base.update(over)
    return ExtractionPayload(**base)


def test_ingest_survives_restart(store, family_id):
    entry = store.ingest(family_id, _payload())
    assert entry.obligation_node_id is not None

    # "Restart": a brand-new store instance over the same database.
    reborn = PersistentHouseholdStore(DSN, MASTER)
    try:
        graph = reborn.graph(family_id)
        assert entry.obligation_node_id in graph.nodes
        node = graph.nodes[entry.obligation_node_id]
        assert node.properties["name"] == "Field Trip Permission Slip"
        assert node.properties["target_person_name"] == "Olivia"
        # Edges (anchor DEPENDS_ON obligation) survive too.
        assert len(graph.edges) == 1
    finally:
        reborn.close()


def test_ledger_survives_restart(store, family_id):
    store.ingest(family_id, _payload())
    store.ingest(family_id, _payload(confidence_score=0.5, extracted_event="Vague note"))

    reborn = PersistentHouseholdStore(DSN, MASTER)
    try:
        entries = reborn.ledger(family_id)
        assert len(entries) == 2
        statuses = {e.decision.status.value for e in entries}
        assert statuses == {"COMMITTED", "REJECTED"}
        assert entries[0].payload.extracted_event == "Field Trip Permission Slip"
    finally:
        reborn.close()


def test_approval_survives_restart(store, family_id):
    entry = store.ingest(family_id, _payload())
    assert len(store.drafts(family_id)) == 1
    store.approve_action(family_id, entry.obligation_node_id)

    reborn = PersistentHouseholdStore(DSN, MASTER)
    try:
        assert reborn.drafts(family_id) == []  # resolved state persisted
        node = reborn.graph(family_id).nodes[entry.obligation_node_id]
        assert node.properties["status"] == "COMPLETED"
    finally:
        reborn.close()


def test_profile_survives_restart(store, family_id):
    store.set_profile(family_id, parent_first_name="Andrew")

    reborn = PersistentHouseholdStore(DSN, MASTER)
    try:
        assert reborn.profile(family_id) == {"parent_first_name": "Andrew"}
    finally:
        reborn.close()


def test_database_stores_no_plaintext(store, family_id):
    store.ingest(family_id, _payload())
    store.set_profile(family_id, parent_first_name="Andrew")

    with psycopg.connect(DSN) as conn:
        for table in ("family_secure_nodes", "family_secure_edges",
                      "extraction_ledger", "families"):
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE family_id = %s", (family_id,)  # noqa: S608
            ).fetchall()
            blob = repr(rows)
            assert "Olivia" not in blob, f"plaintext name leaked in {table}"
            assert "Permission Slip" not in blob, f"plaintext event leaked in {table}"
            assert "Andrew" not in blob, f"plaintext profile leaked in {table}"


def test_wrong_master_secret_fails_loudly(store, family_id):
    store.ingest(family_id, _payload())

    imposter = PersistentHouseholdStore(DSN, "not-the-real-secret")
    try:
        with pytest.raises(ValueError, match="KEK verification failed"):
            imposter.graph(family_id)
    finally:
        imposter.close()


def test_families_are_cryptographically_isolated(store, family_id):
    other = f"fam_{uuid.uuid4().hex[:10]}"
    store.ingest(family_id, _payload())
    assert store.graph(other).nodes == {}

    with psycopg.connect(DSN) as conn:
        salts = conn.execute(
            "SELECT family_id, kek_salt FROM families WHERE family_id IN (%s, %s)",
            (family_id, other),
        ).fetchall()
    # Each family gets its own random salt → its own KEK.
    unique_salts = {bytes(s) for _, s in salts}
    assert len(unique_salts) == len(salts)
