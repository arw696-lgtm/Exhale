"""Postgres persistence for the household store (Blueprint §5.3).

:class:`PersistentHouseholdStore` gives the in-memory
:class:`~exhale.store.HouseholdStore` a durable, **encrypted-at-rest** backing:
every graph node/edge payload, ledger entry, and family profile is routed
through the Zero-Knowledge envelope pipeline (:mod:`exhale.crypto`,
:mod:`exhale.secure`) before it touches the database. The database holds only
ciphertext, nonces, wrapped DEKs, and blind indexes — plus the cleartext graph
*topology* (node/edge types and endpoints) needed for traversal.

Key management (reference implementation): per-family KEKs are derived from a
service master secret + a per-family random salt (PBKDF2). This keeps data
encrypted at rest and per-family isolated. True client-side key custody — where
the KEK never leaves the household's devices (§5.1) — slots in here later by
replacing :class:`ServiceKeyring` with client-supplied keys; nothing else
changes.

Write strategy: family graphs are small (hundreds of nodes), so mutations
persist via full replace of the family's rows in one transaction — simple and
crash-consistent. Swap for row-level upserts if graphs grow large.
"""

from __future__ import annotations

import importlib.resources
import threading

import psycopg

from exhale.crypto import (
    decrypt_payload,
    derive_kek,
    encrypt_payload,
    generate_salt,
    kek_verification_tag,
    verify_kek,
)
from exhale.graph import KnowledgeGraph
from exhale.routing import route_extraction
from exhale.schemas import ExtractionPayload
from exhale.secure import decrypt_edge, decrypt_node, encrypt_edge, encrypt_node
from exhale.store import HouseholdStore, LedgerEntry

_ENVELOPE_COLS = (
    "encrypted_payload_blob", "cryptographic_nonce", "key_verification_tag", "wrapped_dek",
)


def load_schema_sql() -> str:
    """The canonical DDL, shipped inside the package."""

    return (importlib.resources.files("exhale") / "sql" / "schema.sql").read_text()


class ServiceKeyring:
    """Derives and caches per-family KEKs from a service master secret.

    The salt is random per family and stored in ``families.kek_salt``; the
    verification tag proves the derived key matches on later loads.
    """

    def __init__(self, master_secret: str) -> None:
        if not master_secret:
            raise ValueError("master secret must be non-empty")
        self._master_secret = master_secret
        self._cache: dict[str, bytes] = {}

    def kek_for(self, family_id: str, salt: bytes, verify_tag: str | None = None) -> bytes:
        kek = self._cache.get(family_id)
        if kek is None:
            kek = derive_kek(f"{self._master_secret}:{family_id}", salt)
            self._cache[family_id] = kek
        if verify_tag is not None and not verify_kek(kek, verify_tag):
            raise ValueError(
                f"KEK verification failed for family {family_id!r} — wrong master secret?"
            )
        return kek


class PersistentHouseholdStore(HouseholdStore):
    """A :class:`HouseholdStore` whose state survives restarts.

    Reads hydrate lazily from Postgres into the in-memory graph; every mutation
    (ingest / approve / set_graph / set_profile) writes back through the
    encryption pipeline in one transaction.
    """

    def __init__(self, dsn: str, master_secret: str) -> None:
        super().__init__()
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._db_lock = threading.RLock()
        self._keyring = ServiceKeyring(master_secret)
        self._hydrated: set[str] = set()
        with self._db_lock, self._conn.transaction():
            self._conn.execute(load_schema_sql())

    # -- family / key bootstrap ----------------------------------------------
    def _family_kek(self, family_id: str) -> bytes:
        """Fetch-or-create the family row and return its KEK."""

        with self._db_lock:
            row = self._conn.execute(
                "SELECT kek_salt, kek_verify_tag FROM families WHERE family_id = %s",
                (family_id,),
            ).fetchone()
            if row is not None and bytes(row[0]):
                return self._keyring.kek_for(family_id, bytes(row[0]), row[1])

            salt = generate_salt()
            kek = self._keyring.kek_for(family_id, salt)
            if row is None:
                self._conn.execute(
                    "INSERT INTO families (family_id, kek_salt, kek_verify_tag) "
                    "VALUES (%s, %s, %s) ON CONFLICT (family_id) DO NOTHING",
                    (family_id, salt, kek_verification_tag(kek)),
                )
            else:
                # Row pre-created by signup (auth layer) with keys pending —
                # finish cryptographic initialization now.
                self._conn.execute(
                    "UPDATE families SET kek_salt = %s, kek_verify_tag = %s "
                    "WHERE family_id = %s",
                    (salt, kek_verification_tag(kek), family_id),
                )
            return kek

    # -- hydration -------------------------------------------------------------
    def _hydrate(self, family_id: str) -> None:
        """Load a family's graph, ledger, and profile from the DB (once)."""

        with self._lock:
            if family_id in self._hydrated:
                return
            self._hydrated.add(family_id)

        kek = self._family_kek(family_id)
        graph = KnowledgeGraph()

        with self._db_lock:
            node_rows = self._conn.execute(
                "SELECT node_id, family_id, node_type, blind_index_hash, "
                "encrypted_payload_blob, cryptographic_nonce, key_verification_tag, "
                "wrapped_dek FROM family_secure_nodes WHERE family_id = %s",
                (family_id,),
            ).fetchall()
            edge_rows = self._conn.execute(
                "SELECT edge_id, family_id, edge_type, source_node_id, target_node_id, "
                "confidence_score, verified_by_user, encrypted_payload_blob, "
                "cryptographic_nonce, key_verification_tag, wrapped_dek "
                "FROM family_secure_edges WHERE family_id = %s",
                (family_id,),
            ).fetchall()
            ledger_rows = self._conn.execute(
                "SELECT extraction_id, encrypted_payload_blob, cryptographic_nonce, "
                "key_verification_tag, wrapped_dek, obligation_node_id, created_at "
                "FROM extraction_ledger WHERE family_id = %s ORDER BY created_at",
                (family_id,),
            ).fetchall()
            profile_row = self._conn.execute(
                "SELECT encrypted_profile_blob, profile_nonce, profile_tag, "
                "profile_wrapped_dek FROM families WHERE family_id = %s",
                (family_id,),
            ).fetchone()

        node_cols = ("node_id", "family_id", "node_type", "blind_index_hash", *_ENVELOPE_COLS)
        for row in node_rows:
            graph.add_node(decrypt_node(dict(zip(node_cols, row)), kek))
        edge_cols = ("edge_id", "family_id", "edge_type", "source_node_id",
                     "target_node_id", "confidence_score", "verified_by_user", *_ENVELOPE_COLS)
        for row in edge_rows:
            graph.add_edge(decrypt_edge(dict(zip(edge_cols, row)), kek))

        with self._lock:
            if graph.nodes:
                self._graphs[family_id] = graph
            entries = []
            for ext_id, blob, nonce, tag, wdek, ob_id, created in ledger_rows:
                payload_dict = decrypt_payload(
                    _envelope(blob, nonce, tag, wdek), kek
                )
                payload = ExtractionPayload(**payload_dict)
                entry = LedgerEntry(ext_id, payload, route_extraction(payload), ob_id)
                entry.created_at = created
                entries.append(entry)
            if entries:
                # Supersession is derived from payload.corrects, so a user
                # correction's audit trail survives restarts without schema churn.
                self._link_supersessions(entries)
                self._ledger[family_id] = entries
            if profile_row and profile_row[0]:
                self._profiles[family_id] = decrypt_payload(
                    _envelope(*profile_row), kek
                )

    # -- write-back ------------------------------------------------------------
    def _persist_graph(self, family_id: str) -> None:
        kek = self._family_kek(family_id)
        with self._lock:
            graph = self._graphs.get(family_id) or KnowledgeGraph()
            nodes = list(graph.nodes.values())
            edges = list(graph.edges.values())

        with self._db_lock, self._conn.transaction():
            self._conn.execute(
                "DELETE FROM family_secure_edges WHERE family_id = %s", (family_id,)
            )
            self._conn.execute(
                "DELETE FROM family_secure_nodes WHERE family_id = %s", (family_id,)
            )
            for node in nodes:
                row = encrypt_node(
                    node, family_id, kek,
                    index_value=str(node.properties.get("name", node.node_id)),
                )
                self._conn.execute(
                    "INSERT INTO family_secure_nodes (node_id, family_id, node_type, "
                    "blind_index_hash, encrypted_payload_blob, cryptographic_nonce, "
                    "key_verification_tag, wrapped_dek) "
                    "VALUES (%(node_id)s, %(family_id)s, %(node_type)s, "
                    "%(blind_index_hash)s, %(encrypted_payload_blob)s, "
                    "%(cryptographic_nonce)s, %(key_verification_tag)s, %(wrapped_dek)s)",
                    row,
                )
            for edge in edges:
                row = encrypt_edge(edge, family_id, kek)
                self._conn.execute(
                    "INSERT INTO family_secure_edges (edge_id, family_id, edge_type, "
                    "source_node_id, target_node_id, confidence_score, verified_by_user, "
                    "encrypted_payload_blob, cryptographic_nonce, key_verification_tag, "
                    "wrapped_dek) "
                    "VALUES (%(edge_id)s, %(family_id)s, %(edge_type)s, "
                    "%(source_node_id)s, %(target_node_id)s, %(confidence_score)s, "
                    "%(verified_by_user)s, %(encrypted_payload_blob)s, "
                    "%(cryptographic_nonce)s, %(key_verification_tag)s, %(wrapped_dek)s)",
                    row,
                )

    def _persist_ledger_entry(self, family_id: str, entry: LedgerEntry) -> None:
        kek = self._family_kek(family_id)
        env = encrypt_payload(entry.payload.model_dump(mode="json"), kek)
        with self._db_lock:
            self._conn.execute(
                "INSERT INTO extraction_ledger (extraction_id, family_id, "
                "confidence_score, confidence_band, record_status, source_channel, "
                "source_reference, source_document_name, obligation_node_id, "
                "encrypted_payload_blob, cryptographic_nonce, key_verification_tag, "
                "wrapped_dek, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    entry.extraction_id, family_id,
                    entry.payload.confidence_score, entry.decision.band.value,
                    entry.decision.status.value, "api",
                    entry.payload.source_reference, entry.payload.source_document_name,
                    entry.obligation_node_id,
                    env.encrypted_payload_blob, env.cryptographic_nonce,
                    env.key_verification_tag, env.wrapped_dek, entry.created_at,
                ),
            )

    # -- HouseholdStore surface, made durable ----------------------------------
    def graph(self, family_id: str) -> KnowledgeGraph:
        self._hydrate(family_id)
        return super().graph(family_id)

    def set_graph(self, family_id: str, graph: KnowledgeGraph) -> None:
        self._hydrate(family_id)
        super().set_graph(family_id, graph)
        self._persist_graph(family_id)

    def ledger(self, family_id: str) -> list[LedgerEntry]:
        self._hydrate(family_id)
        return super().ledger(family_id)

    def profile(self, family_id: str) -> dict:
        self._hydrate(family_id)
        return super().profile(family_id)

    def set_profile(self, family_id: str, **profile) -> None:
        self._hydrate(family_id)
        super().set_profile(family_id, **profile)
        kek = self._family_kek(family_id)
        env = encrypt_payload(super().profile(family_id), kek)
        with self._db_lock:
            self._conn.execute(
                "UPDATE families SET encrypted_profile_blob = %s, profile_nonce = %s, "
                "profile_tag = %s, profile_wrapped_dek = %s WHERE family_id = %s",
                (env.encrypted_payload_blob, env.cryptographic_nonce,
                 env.key_verification_tag, env.wrapped_dek, family_id),
            )

    def ingest(self, family_id: str, payload: ExtractionPayload) -> LedgerEntry:
        self._hydrate(family_id)
        entry = super().ingest(family_id, payload)
        self._persist_graph(family_id)
        self._persist_ledger_entry(family_id, entry)
        return entry

    def correct(self, family_id: str, extraction_id: str, **fixes) -> LedgerEntry:
        self._hydrate(family_id)
        entry = super().correct(family_id, extraction_id, **fixes)
        self._persist_graph(family_id)
        self._persist_ledger_entry(family_id, entry)
        return entry

    def drafts(self, family_id: str):
        self._hydrate(family_id)
        return super().drafts(family_id)

    def approve_action(self, family_id: str, obligation_node_id: str, *, resolution: str = "COMPLETED") -> None:
        self._hydrate(family_id)
        super().approve_action(family_id, obligation_node_id, resolution=resolution)
        self._persist_graph(family_id)

    def family_ids(self) -> list[str]:
        with self._db_lock:
            rows = self._conn.execute("SELECT family_id FROM families").fetchall()
        return sorted({r[0] for r in rows} | set(super().family_ids()))

    def close(self) -> None:
        self._conn.close()


def _envelope(blob: str, nonce: str, tag: str, wrapped_dek: str):
    from exhale.crypto import EncryptedEnvelope

    return EncryptedEnvelope(
        encrypted_payload_blob=blob,
        cryptographic_nonce=nonce,
        key_verification_tag=tag,
        wrapped_dek=wrapped_dek,
    )
