"""Tests for the graph <-> encrypted-storage bridge (§5.3)."""

import json

import pytest
from cryptography.exceptions import InvalidTag

from exhale.crypto import blind_index, derive_kek
from exhale.graph import Node, NodeType
from exhale.secure import decrypt_node, encrypt_node

KEK = derive_kek("household passphrase", b"\x11" * 16)
OTHER_KEK = derive_kek("someone else", b"\x22" * 16)

NODE = Node(
    node_id="node_child_olivia_001",
    type=NodeType.PERSON,
    sub_type="CHILD",
    properties={"first_name": "Olivia", "date_of_birth": "2018-04-12", "allergies": ["Peanuts"]},
)


def test_encrypt_then_decrypt_roundtrips_the_node():
    row = encrypt_node(NODE, "family_001", KEK, index_value="Olivia")
    restored = decrypt_node(row, KEK)
    assert restored.node_id == NODE.node_id
    assert restored.type is NodeType.PERSON
    assert restored.sub_type == "CHILD"
    assert restored.properties == NODE.properties


def test_node_type_is_cleartext_but_details_are_sealed():
    row = encrypt_node(NODE, "family_001", KEK, index_value="Olivia")
    assert row["node_type"] == "PERSON"  # routing type visible
    serialized = json.dumps(row)
    assert "Olivia" not in serialized     # name sealed
    assert "Peanuts" not in serialized    # allergies sealed
    assert "CHILD" not in serialized      # sub_type sealed


def test_row_has_all_secure_columns():
    row = encrypt_node(NODE, "family_001", KEK, index_value="Olivia")
    for col in (
        "node_id", "family_id", "node_type", "blind_index_hash",
        "encrypted_payload_blob", "cryptographic_nonce",
        "key_verification_tag", "wrapped_dek",
    ):
        assert col in row


def test_blind_index_supports_equality_lookup():
    row = encrypt_node(NODE, "family_001", KEK, index_value="Olivia")
    # A query builds the same blind index from the search term.
    assert row["blind_index_hash"] == blind_index(KEK, "olivia")


def test_wrong_family_key_cannot_decrypt():
    row = encrypt_node(NODE, "family_001", KEK, index_value="Olivia")
    with pytest.raises(InvalidTag):
        decrypt_node(row, OTHER_KEK)
