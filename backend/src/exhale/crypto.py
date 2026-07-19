"""Zero-Knowledge Core — client-side envelope encryption (Blueprint §5).

Implements the cryptographic pipeline described in §5.2 so that the columns in
``db/schema.sql`` are actually producible:

1. **Master Key Derivation** — a 256-bit Key Encrypting Key (KEK) is derived from
   a household passphrase + per-family salt via PBKDF2-HMAC-SHA256.
2. **Symmetric Payload Shielding** — each entity payload is encrypted with a
   fresh, ephemeral Data Encryption Key (DEK) using AES-GCM-256.
3. **Database Envelope Layout** — the DEK is itself wrapped with the KEK; the
   persistence engine receives only the encrypted payload, nonces, wrapped-DEK
   token, and auth tag. It never sees plaintext or the KEK.

Queries over encrypted data use a **blind index**: a keyed HMAC of a normalized
value, deterministic per-family so equality lookups work without leaking data.

All key material lives only in process memory here (the reference "client"); in
production this module runs on-device and only the :class:`EncryptedEnvelope`
fields cross the network.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Tunable cryptographic parameters ----------------------------------------
PBKDF2_ITERATIONS = 600_000  # OWASP-aligned for PBKDF2-HMAC-SHA256.
KEK_LENGTH = 32              # 256-bit Key Encrypting Key.
DEK_LENGTH = 32             # 256-bit Data Encryption Key.
NONCE_LENGTH = 12           # 96-bit GCM nonce (recommended).
SALT_LENGTH = 16

# Domain-separation labels so keys derived from the same KEK never collide.
_BLIND_INDEX_LABEL = b"exhale/blind-index/v1"
_KEK_VERIFY_LABEL = b"exhale/kek-verify/v1"


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# --- Key derivation -----------------------------------------------------------
def generate_salt() -> bytes:
    """Return a fresh cryptographic salt for a new family."""

    return os.urandom(SALT_LENGTH)


def derive_kek(passphrase: str, salt: bytes) -> bytes:
    """Derive the 256-bit KEK from a passphrase + salt (§5.2 step 1)."""

    if not passphrase:
        raise ValueError("passphrase must be non-empty")
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=KEK_LENGTH
    )


def kek_verification_tag(kek: bytes) -> str:
    """A tag proving passphrase correctness without storing the KEK.

    Stored in ``families.kek_verify_tag``; recomputed and compared on unlock.
    Hex-encoded HMAC-SHA256 → 64 chars, matching ``VARCHAR(64)``.
    """

    return hmac.new(kek, _KEK_VERIFY_LABEL, hashlib.sha256).hexdigest()


def verify_kek(kek: bytes, expected_tag: str) -> bool:
    """Constant-time check that ``kek`` matches a stored verification tag."""

    return hmac.compare_digest(kek_verification_tag(kek), expected_tag)


def _derive_blind_index_key(kek: bytes) -> bytes:
    """Derive a stable, domain-separated blind-index key from the KEK."""

    return hmac.new(kek, _BLIND_INDEX_LABEL, hashlib.sha256).digest()


def blind_index(kek: bytes, value: str) -> str:
    """Deterministic keyed hash of a normalized value (§5.3 blind index).

    Case/space-insensitive equality lookups without plaintext leakage. Returns a
    64-char hex string matching ``blind_index_hash CHAR(64)``.
    """

    normalized = " ".join(value.strip().lower().split()).encode("utf-8")
    key = _derive_blind_index_key(kek)
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


# --- Envelope encryption ------------------------------------------------------
@dataclass(frozen=True)
class EncryptedEnvelope:
    """The persisted, plaintext-free representation of one payload.

    Fields map 1:1 onto ``db/schema.sql`` columns:

    * ``encrypted_payload_blob``  → ``encrypted_payload_blob TEXT``
    * ``cryptographic_nonce``     → ``cryptographic_nonce VARCHAR(24)``
    * ``key_verification_tag``    → ``key_verification_tag VARCHAR(32)``
    * ``wrapped_dek``             → ``wrapped_dek VARCHAR(96)``
    """

    encrypted_payload_blob: str  # base64(ciphertext)
    cryptographic_nonce: str     # base64(12-byte payload nonce)
    key_verification_tag: str    # base64(16-byte GCM auth tag)
    wrapped_dek: str             # base64(nonce || wrapped-DEK-ciphertext || tag)

    def to_columns(self) -> dict[str, str]:
        return {
            "encrypted_payload_blob": self.encrypted_payload_blob,
            "cryptographic_nonce": self.cryptographic_nonce,
            "key_verification_tag": self.key_verification_tag,
            "wrapped_dek": self.wrapped_dek,
        }

    @classmethod
    def from_columns(cls, columns: dict[str, str]) -> "EncryptedEnvelope":
        return cls(
            encrypted_payload_blob=columns["encrypted_payload_blob"],
            cryptographic_nonce=columns["cryptographic_nonce"],
            key_verification_tag=columns["key_verification_tag"],
            wrapped_dek=columns["wrapped_dek"],
        )


def encrypt_payload(payload: Any, kek: bytes) -> EncryptedEnvelope:
    """Encrypt a JSON-serializable payload under a fresh DEK (§5.2 steps 2-3)."""

    plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    # Step 2: encrypt payload with an ephemeral DEK.
    dek = os.urandom(DEK_LENGTH)
    payload_nonce = os.urandom(NONCE_LENGTH)
    sealed = AESGCM(dek).encrypt(payload_nonce, plaintext, None)
    ciphertext, auth_tag = sealed[:-16], sealed[-16:]

    # Step 3: wrap the DEK with the KEK; pack nonce||ct||tag into one token.
    dek_nonce = os.urandom(NONCE_LENGTH)
    wrapped = AESGCM(kek).encrypt(dek_nonce, dek, None)

    return EncryptedEnvelope(
        encrypted_payload_blob=_b64e(ciphertext),
        cryptographic_nonce=_b64e(payload_nonce),
        key_verification_tag=_b64e(auth_tag),
        wrapped_dek=_b64e(dek_nonce + wrapped),
    )


def decrypt_payload(envelope: EncryptedEnvelope, kek: bytes) -> Any:
    """Reverse :func:`encrypt_payload`. Raises ``InvalidTag`` on tamper/wrong key."""

    token = _b64d(envelope.wrapped_dek)
    dek_nonce, wrapped = token[:NONCE_LENGTH], token[NONCE_LENGTH:]
    dek = AESGCM(kek).decrypt(dek_nonce, wrapped, None)

    ciphertext = _b64d(envelope.encrypted_payload_blob)
    auth_tag = _b64d(envelope.key_verification_tag)
    payload_nonce = _b64d(envelope.cryptographic_nonce)
    plaintext = AESGCM(dek).decrypt(payload_nonce, ciphertext + auth_tag, None)

    return json.loads(plaintext.decode("utf-8"))
