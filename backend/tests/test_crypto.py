"""Tests for the Zero-Knowledge envelope-encryption layer (§5)."""

import json

import pytest
from cryptography.exceptions import InvalidTag

from exhale.crypto import (
    blind_index,
    decrypt_payload,
    derive_kek,
    encrypt_payload,
    generate_salt,
    kek_verification_tag,
    verify_kek,
)

PASSPHRASE = "correct horse battery staple"
PAYLOAD = {"first_name": "Olivia", "allergies": ["Peanuts"], "grade_level": 3}


def _kek(passphrase=PASSPHRASE, salt=None):
    return derive_kek(passphrase, salt or b"\x00" * 16)


def test_roundtrip():
    kek = _kek()
    env = encrypt_payload(PAYLOAD, kek)
    assert decrypt_payload(env, kek) == PAYLOAD


def test_kek_is_deterministic_for_same_passphrase_and_salt():
    salt = generate_salt()
    assert derive_kek(PASSPHRASE, salt) == derive_kek(PASSPHRASE, salt)


def test_kek_differs_with_salt():
    assert derive_kek(PASSPHRASE, generate_salt()) != derive_kek(PASSPHRASE, generate_salt())


def test_empty_passphrase_rejected():
    with pytest.raises(ValueError):
        derive_kek("", generate_salt())


def test_wrong_passphrase_cannot_decrypt():
    env = encrypt_payload(PAYLOAD, _kek())
    wrong = _kek(passphrase="wrong passphrase")
    with pytest.raises(InvalidTag):
        decrypt_payload(env, wrong)


def test_tampered_ciphertext_is_detected():
    kek = _kek()
    env = encrypt_payload(PAYLOAD, kek)
    # Flip a byte in the ciphertext blob.
    import base64

    raw = bytearray(base64.b64decode(env.encrypted_payload_blob))
    raw[0] ^= 0x01
    tampered = env.__class__(
        encrypted_payload_blob=base64.b64encode(bytes(raw)).decode(),
        cryptographic_nonce=env.cryptographic_nonce,
        key_verification_tag=env.key_verification_tag,
        wrapped_dek=env.wrapped_dek,
    )
    with pytest.raises(InvalidTag):
        decrypt_payload(tampered, kek)


def test_nonce_and_blob_differ_across_encryptions():
    kek = _kek()
    a = encrypt_payload(PAYLOAD, kek)
    b = encrypt_payload(PAYLOAD, kek)
    # Fresh DEK + nonce each time → different ciphertext and wrapped key.
    assert a.encrypted_payload_blob != b.encrypted_payload_blob
    assert a.cryptographic_nonce != b.cryptographic_nonce
    assert a.wrapped_dek != b.wrapped_dek


def test_kek_verification_tag_roundtrip():
    kek = _kek()
    tag = kek_verification_tag(kek)
    assert verify_kek(kek, tag) is True
    assert verify_kek(_kek(passphrase="nope"), tag) is False


# --- blind index -------------------------------------------------------------
def test_blind_index_is_deterministic():
    kek = _kek()
    assert blind_index(kek, "Olivia") == blind_index(kek, "Olivia")


def test_blind_index_normalizes_case_and_whitespace():
    kek = _kek()
    assert blind_index(kek, "  Olivia   Chen ") == blind_index(kek, "olivia chen")


def test_blind_index_differs_across_families():
    fam_a = derive_kek(PASSPHRASE, generate_salt())
    fam_b = derive_kek(PASSPHRASE, generate_salt())
    assert blind_index(fam_a, "Olivia") != blind_index(fam_b, "Olivia")


# --- schema column-length contracts (db/schema.sql) --------------------------
def test_envelope_fields_fit_schema_columns():
    env = encrypt_payload(PAYLOAD, _kek())
    assert len(env.cryptographic_nonce) <= 24      # VARCHAR(24)
    assert len(env.key_verification_tag) <= 32     # VARCHAR(32)
    assert len(env.wrapped_dek) <= 96              # VARCHAR(96)
    assert len(blind_index(_kek(), "Olivia")) == 64  # CHAR(64)


def test_columns_contain_no_plaintext():
    kek = _kek()
    env = encrypt_payload(PAYLOAD, kek)
    serialized = json.dumps(env.to_columns())
    assert "Olivia" not in serialized
    assert "Peanuts" not in serialized
