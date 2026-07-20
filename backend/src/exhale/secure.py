"""Bridge between the graph model and the Zero-Knowledge storage layer (§5.3).

Turns a plaintext :class:`~exhale.graph.Node` into the exact column set of
``family_secure_nodes`` — an encrypted envelope plus a cleartext routing
``node_type`` and a blind index — and reconstructs the node on read.

Only ``node_type`` stays in cleartext (so the engine can traverse graph *shape*
without decrypting); ``sub_type``, ``properties``, and ``metadata`` are sealed
inside the envelope. The blind index is computed over a caller-chosen indexable
value (e.g. a person's name) to support equality lookups without leakage.
"""

from __future__ import annotations

from exhale.crypto import EncryptedEnvelope, blind_index, decrypt_payload, encrypt_payload
from exhale.graph import Edge, EdgeType, Node, NodeType


def encrypt_node(
    node: Node,
    family_id: str,
    kek: bytes,
    *,
    index_value: str | None = None,
) -> dict:
    """Return a ``family_secure_nodes`` row dict for ``node``.

    ``index_value`` is the plaintext used to build the blind index; when omitted
    it defaults to the node id (still non-reversible once hashed).
    """

    sealed_payload = {
        "sub_type": node.sub_type,
        "properties": node.properties,
        "metadata": node.metadata.model_dump(mode="json"),
    }
    envelope = encrypt_payload(sealed_payload, kek)

    row = {
        "node_id": node.node_id,
        "family_id": family_id,
        "node_type": node.type.value,  # cleartext routing type
        "blind_index_hash": blind_index(kek, index_value or node.node_id),
        **envelope.to_columns(),
    }
    return row


def decrypt_node(row: dict, kek: bytes) -> Node:
    """Reconstruct a :class:`Node` from a ``family_secure_nodes`` row dict."""

    envelope = EncryptedEnvelope.from_columns(row)
    sealed = decrypt_payload(envelope, kek)
    return Node(
        node_id=row["node_id"],
        type=NodeType(row["node_type"]),
        sub_type=sealed.get("sub_type"),
        properties=sealed.get("properties", {}),
        metadata=sealed.get("metadata", {}),
    )


def encrypt_edge(edge: Edge, family_id: str, kek: bytes) -> dict:
    """Return a ``family_secure_edges`` row dict for ``edge``.

    Topology (type, endpoints) and routing metadata stay cleartext so the
    engine can traverse graph shape; edge ``properties`` are sealed.
    """

    envelope = encrypt_payload({"properties": edge.properties}, kek)
    return {
        "edge_id": edge.edge_id,
        "family_id": family_id,
        "edge_type": edge.type.value,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "confidence_score": edge.metadata.confidence_score,
        "verified_by_user": edge.metadata.verified_by_user,
        **envelope.to_columns(),
    }


def decrypt_edge(row: dict, kek: bytes) -> Edge:
    """Reconstruct an :class:`Edge` from a ``family_secure_edges`` row dict."""

    envelope = EncryptedEnvelope.from_columns(row)
    sealed = decrypt_payload(envelope, kek)
    return Edge(
        edge_id=row["edge_id"],
        type=EdgeType(row["edge_type"]),
        source_node_id=row["source_node_id"],
        target_node_id=row["target_node_id"],
        properties=sealed.get("properties", {}),
        metadata={
            "confidence_score": float(row["confidence_score"]),
            "verified_by_user": row["verified_by_user"],
        },
    )
