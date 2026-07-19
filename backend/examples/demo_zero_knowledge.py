"""Demo: the Zero-Knowledge Core in action (Blueprint §5).

Shows that a family node can be encrypted on-device into the exact
``family_secure_nodes`` column set, that the persisted row carries no plaintext,
and that only the correct household KEK can read it back.

Usage::

    cd backend && PYTHONPATH=src python examples/demo_zero_knowledge.py
"""

from __future__ import annotations

import json

from exhale.crypto import derive_kek, generate_salt, kek_verification_tag, verify_kek
from exhale.graph import Node, NodeType
from exhale.secure import decrypt_node, encrypt_node


def main() -> None:
    # --- Client device: derive the KEK from the household passphrase ----------
    salt = generate_salt()
    kek = derive_kek("our-family-passphrase", salt)
    verify_tag = kek_verification_tag(kek)  # stored in families.kek_verify_tag
    print("KEK verification tag:", verify_tag)
    print("Passphrase check on unlock:", verify_kek(kek, verify_tag))

    # --- Encrypt a child profile node for storage -----------------------------
    olivia = Node(
        node_id="node_child_olivia_001",
        type=NodeType.PERSON,
        sub_type="CHILD",
        properties={"first_name": "Olivia", "date_of_birth": "2018-04-12", "allergies": ["Peanuts"]},
    )
    row = encrypt_node(olivia, "family_demo_001", kek, index_value="Olivia")

    print("\nWhat the cloud database actually stores (zero plaintext):")
    print(json.dumps(row, indent=2))

    # --- Read back with the correct key ---------------------------------------
    restored = decrypt_node(row, kek)
    print("\nDecrypted on-device:", restored.properties)

    # --- A different family's key is useless ----------------------------------
    attacker_kek = derive_kek("guessed-passphrase", generate_salt())
    try:
        decrypt_node(row, attacker_kek)
    except Exception as exc:  # noqa: BLE001 - illustrative
        print(f"\nWrong key rejected: {type(exc).__name__}")


if __name__ == "__main__":
    main()
