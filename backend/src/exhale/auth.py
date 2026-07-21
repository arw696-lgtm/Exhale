"""Accounts, sessions, and family-scoped access control (Part 3).

Design:

* **Passwords** — PBKDF2-HMAC-SHA256 (600k iterations, random per-user salt),
  same cost profile as the §5 KEK derivation. Only hash + salt are stored.
* **Sessions** — opaque bearer tokens (``secrets.token_urlsafe``); the database
  stores only the SHA-256 hash of the token, so a DB leak reveals no usable
  credentials. Tokens expire after 30 days.
* **Families** — signup either creates a fresh family or joins an existing one
  via its **invite code** (the low-friction caregiver invite loop, §13.2).
* **Backends** — :class:`InMemoryAuthStore` for dev/tests and
  :class:`PostgresAuthStore` for production, matching the household-store split.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PBKDF2_ITERATIONS = 600_000
SESSION_TTL = timedelta(days=30)


# --- password + token primitives (pure) --------------------------------------
def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return ``(hash_hex, salt_hex)`` for storage."""

    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest.hex(), hash_hex)


def new_session_token() -> tuple[str, str]:
    """Return ``(token, token_hash)`` — the token goes to the client only."""

    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_invite_code() -> str:
    """Human-friendly family invite code.

    Consonants + digits only: avoids ambiguous glyphs (0/O, 1/I/L) and keeps
    random codes from accidentally spelling words.
    """

    alphabet = "BCDFGHJKMNPQRSTVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


# Membership roles (FAMILY_STRUCTURES §3.2). A MEMBER is a full adult of the
# household — mutual visibility, can invite others. A HELPER is a scoped
# secondary caregiver (grandparent, regular sitter): they see only their care
# days and items the household explicitly shares (enforced in the API, not here).
ROLE_MEMBER = "MEMBER"
ROLE_HELPER = "HELPER"


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    display_name: str
    family_id: str
    role: str = ROLE_MEMBER


@dataclass(frozen=True)
class InviteInfo:
    """What a code grants: which family, and as what kind of member."""

    family_id: str
    kind: str  # "family" | "helper"
    weekdays: tuple[int, ...] = ()  # helper invites only: 0=Mon .. 6=Sun


class AuthError(Exception):
    """Signup/login failure with a user-safe message."""


# --- in-memory backend --------------------------------------------------------
class InMemoryAuthStore:
    """Volatile auth backend for dev and tests."""

    def __init__(self) -> None:
        self._users: dict[str, dict] = {}          # user_id -> record
        self._by_email: dict[str, str] = {}        # email -> user_id
        self._sessions: dict[str, dict] = {}       # token_hash -> {user_id, expires_at}
        self._invites: dict[str, str] = {}         # invite_code -> family_id
        self._family_invites: dict[str, str] = {}  # family_id -> invite_code
        self._helper_invites: dict[str, dict] = {} # code -> {family_id, weekdays}
        self._lock = threading.RLock()

    # -- signup / login -------------------------------------------------------
    def signup(self, email: str, password: str, display_name: str,
               invite_code: str | None = None) -> tuple[User, str]:
        email = email.strip().lower()
        pw_hash, pw_salt = hash_password(password)
        with self._lock:
            if email in self._by_email:
                raise AuthError("An account with this email already exists")
            role = ROLE_MEMBER
            if invite_code:
                info = self._resolve_invite(invite_code)
                if info is None:
                    raise AuthError("Invalid invite code")
                family_id = info.family_id
                role = ROLE_HELPER if info.kind == "helper" else ROLE_MEMBER
            else:
                family_id = f"family_{uuid.uuid4().hex[:10]}"
                code = new_invite_code()
                self._invites[code] = family_id
                self._family_invites[family_id] = code

            user_id = f"user_{uuid.uuid4().hex[:10]}"
            self._users[user_id] = {
                "user_id": user_id, "email": email, "display_name": display_name,
                "family_id": family_id, "pw_hash": pw_hash, "pw_salt": pw_salt,
                "role": role,
            }
            self._by_email[email] = user_id
        return self._to_user(user_id), self._create_session(user_id)

    def _resolve_invite(self, code: str) -> InviteInfo | None:
        code = code.strip().upper()
        family_id = self._invites.get(code)
        if family_id is not None:
            return InviteInfo(family_id=family_id, kind="family")
        helper = self._helper_invites.get(code)
        if helper is not None:
            return InviteInfo(family_id=helper["family_id"], kind="helper",
                              weekdays=tuple(helper["weekdays"]))
        return None

    def login(self, email: str, password: str) -> tuple[User, str]:
        email = email.strip().lower()
        with self._lock:
            user_id = self._by_email.get(email)
            record = self._users.get(user_id) if user_id else None
        if record is None or not verify_password(password, record["pw_hash"], record["pw_salt"]):
            raise AuthError("Invalid email or password")
        return self._to_user(user_id), self._create_session(user_id)

    # -- sessions -------------------------------------------------------------
    def _create_session(self, user_id: str) -> str:
        token, token_hash = new_session_token()
        with self._lock:
            self._sessions[token_hash] = {
                "user_id": user_id,
                "expires_at": datetime.now(timezone.utc) + SESSION_TTL,
            }
        return token

    def user_for_token(self, token: str) -> User | None:
        with self._lock:
            session = self._sessions.get(hash_token(token))
            if session is None or session["expires_at"] < datetime.now(timezone.utc):
                return None
            return self._to_user(session["user_id"])

    def revoke_token(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(hash_token(token), None)

    # -- family invites -------------------------------------------------------
    def invite_code_for(self, family_id: str) -> str | None:
        with self._lock:
            return self._family_invites.get(family_id)

    # -- helper invites (scoped secondary caregivers) -------------------------
    def create_helper_invite(self, family_id: str, weekdays) -> str:
        code = new_invite_code()
        with self._lock:
            self._helper_invites[code] = {
                "family_id": family_id, "weekdays": sorted(set(weekdays)),
            }
        return code

    def invite_info(self, code: str) -> InviteInfo | None:
        with self._lock:
            return self._resolve_invite(code)

    def _to_user(self, user_id: str) -> User:
        r = self._users[user_id]
        return User(user_id=r["user_id"], email=r["email"],
                    display_name=r["display_name"], family_id=r["family_id"],
                    role=r.get("role", ROLE_MEMBER))


# --- Postgres backend ---------------------------------------------------------
class PostgresAuthStore:
    """Durable auth backend; shares the schema in ``sql/schema.sql``."""

    def __init__(self, dsn: str) -> None:
        import psycopg

        from exhale.persistence import load_schema_sql

        self._conn = psycopg.connect(dsn, autocommit=True)
        self._lock = threading.RLock()
        with self._lock, self._conn.transaction():
            self._conn.execute(load_schema_sql())

    def signup(self, email: str, password: str, display_name: str,
               invite_code: str | None = None) -> tuple[User, str]:
        email = email.strip().lower()
        pw_hash, pw_salt = hash_password(password)
        with self._lock, self._conn.transaction():
            exists = self._conn.execute(
                "SELECT 1 FROM users WHERE email = %s", (email,)
            ).fetchone()
            if exists:
                raise AuthError("An account with this email already exists")

            role = ROLE_MEMBER
            if invite_code:
                info = self._resolve_invite_locked(invite_code)
                if info is None:
                    raise AuthError("Invalid invite code")
                family_id = info.family_id
                role = ROLE_HELPER if info.kind == "helper" else ROLE_MEMBER
            else:
                family_id = f"family_{uuid.uuid4().hex[:10]}"
                # Family row is created lazily by the household store; here we
                # need it now to hold the invite code. Salt fields are filled by
                # the household store's keyring on first data write.
                self._conn.execute(
                    "INSERT INTO families (family_id, kek_salt, kek_verify_tag, invite_code) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (family_id) DO NOTHING",
                    (family_id, b"", "pending", new_invite_code()),
                )

            user_id = f"user_{uuid.uuid4().hex[:10]}"
            self._conn.execute(
                "INSERT INTO users (user_id, email, display_name, family_id, "
                "password_hash, password_salt, role) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, email, display_name, family_id, pw_hash, pw_salt, role),
            )
        user = User(user_id=user_id, email=email, display_name=display_name,
                    family_id=family_id, role=role)
        return user, self._create_session(user_id)

    def _resolve_invite_locked(self, code: str) -> InviteInfo | None:
        """Resolve a family or helper code. Caller holds the lock."""

        code = code.strip().upper()
        row = self._conn.execute(
            "SELECT family_id FROM families WHERE invite_code = %s", (code,)
        ).fetchone()
        if row is not None:
            return InviteInfo(family_id=row[0], kind="family")
        row = self._conn.execute(
            "SELECT family_id, weekdays FROM helper_invites WHERE code = %s", (code,)
        ).fetchone()
        if row is not None:
            weekdays = tuple(int(d) for d in row[1].split(",") if d != "")
            return InviteInfo(family_id=row[0], kind="helper", weekdays=weekdays)
        return None

    def create_helper_invite(self, family_id: str, weekdays) -> str:
        code = new_invite_code()
        packed = ",".join(str(d) for d in sorted(set(weekdays)))
        with self._lock, self._conn.transaction():
            self._conn.execute(
                "INSERT INTO helper_invites (code, family_id, weekdays) "
                "VALUES (%s, %s, %s)",
                (code, family_id, packed),
            )
        return code

    def invite_info(self, code: str) -> InviteInfo | None:
        with self._lock:
            return self._resolve_invite_locked(code)

    def login(self, email: str, password: str) -> tuple[User, str]:
        email = email.strip().lower()
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, display_name, family_id, password_hash, password_salt, "
                "COALESCE(role, %s) FROM users WHERE email = %s", (ROLE_MEMBER, email)
            ).fetchone()
        if row is None or not verify_password(password, row[3], row[4]):
            raise AuthError("Invalid email or password")
        user = User(user_id=row[0], email=email, display_name=row[1],
                    family_id=row[2], role=row[5])
        return user, self._create_session(row[0])

    def _create_session(self, user_id: str) -> str:
        token, token_hash = new_session_token()
        with self._lock:
            self._conn.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
                "VALUES (%s, %s, %s)",
                (token_hash, user_id, datetime.now(timezone.utc) + SESSION_TTL),
            )
        return token

    def user_for_token(self, token: str) -> User | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT u.user_id, u.email, u.display_name, u.family_id, "
                "COALESCE(u.role, %s) "
                "FROM auth_sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > %s",
                (ROLE_MEMBER, hash_token(token), datetime.now(timezone.utc)),
            ).fetchone()
        if row is None:
            return None
        return User(user_id=row[0], email=row[1], display_name=row[2],
                    family_id=row[3], role=row[4])

    def revoke_token(self, token: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash = %s", (hash_token(token),)
            )

    def invite_code_for(self, family_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT invite_code FROM families WHERE family_id = %s", (family_id,)
            ).fetchone()
        return row[0] if row else None
