"""Exhale HTTP service (FastAPI) — Layer 6 seam over the analytical core.

Exposes the ingestion → routing → graph → briefing path as a small REST API:

* ``GET  /health``                     — liveness.
* ``POST /v1/families/{fid}/extractions`` — ingest an extraction; returns the
  routing decision (§3.3) and any obligation committed to the graph.
* ``GET  /v1/families/{fid}/briefing``  — the Weekly COO Briefing (§9.1).
* ``GET  /v1/families/{fid}/ledger``    — the extraction ledger for the family.

A demo household is seeded at startup so the frontend renders a live briefing
out of the box. Run with::

    cd backend && PYTHONPATH=src uvicorn exhale.api:app --reload
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from exhale import __version__
from exhale.auth import AuthError, InMemoryAuthStore, User
from exhale.briefing import build_weekly_briefing
from exhale.connectors.base import RawMessage
from exhale.connectors.memory import FixtureConnector
from exhale.extraction import ExtractionContext
from exhale.retro_scan import run_incremental_sync, run_retro_scan
from exhale.schemas import ExtractionPayload
from exhale.seed import DEMO_FAMILY_ID, seed_demo
from exhale.store import HouseholdStore

def _build_store() -> HouseholdStore:
    """Choose the store backend from the environment.

    ``EXHALE_DATABASE_URL`` set → encrypted Postgres persistence (§5.3);
    unset → volatile in-memory store (dev/tests).
    """

    import os

    dsn = os.environ.get("EXHALE_DATABASE_URL")
    if not dsn:
        return HouseholdStore()
    from exhale.persistence import PersistentHouseholdStore

    master_secret = os.environ.get("EXHALE_MASTER_SECRET")
    if not master_secret:
        raise RuntimeError(
            "EXHALE_MASTER_SECRET must be set when EXHALE_DATABASE_URL is used — "
            "it protects every family's encryption keys."
        )
    return PersistentHouseholdStore(dsn, master_secret)


def _build_auth_store():
    import os

    dsn = os.environ.get("EXHALE_DATABASE_URL")
    if not dsn:
        return InMemoryAuthStore()
    from exhale.auth import PostgresAuthStore

    return PostgresAuthStore(dsn)


def _build_extractor():
    """Deterministic extractor by default; LLM hybrid when configured (§3)."""

    from exhale.extraction_llm import extractor_from_env

    return extractor_from_env()


store = _build_store()
auth_store = _build_auth_store()
pipeline_extractor = _build_extractor()
# Seed the demo household only if absent, so state (e.g. approved obligations)
# survives service restarts under the persistent backend.
if not store.graph(DEMO_FAMILY_ID).nodes:
    seed_demo(store)
    store.set_profile(DEMO_FAMILY_ID, parent_first_name="Andrew")


# --- auth plumbing ------------------------------------------------------------
def _auth_required() -> bool:
    """Enforcement flag, read per-request so deployments and tests control it.

    Defaults ON when a database is configured (production posture), OFF for the
    in-memory dev mode. Override either way with EXHALE_REQUIRE_AUTH=1/0.
    """

    import os

    flag = os.environ.get("EXHALE_REQUIRE_AUTH")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes")
    return bool(os.environ.get("EXHALE_DATABASE_URL"))


def current_user(authorization: str | None = Header(default=None)) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return auth_store.user_for_token(authorization.split(" ", 1)[1])


def require_family_access(
    family_id: str, user: User | None = Depends(current_user)
) -> str:
    """Guard for /v1/families/{family_id}/* — the token's family must match."""

    if user is not None:
        if user.family_id != family_id:
            raise HTTPException(status_code=403, detail="Not a member of this family")
        return family_id
    if _auth_required():
        raise HTTPException(status_code=401, detail="Authentication required")
    return family_id

app = FastAPI(
    title="Exhale API",
    version=__version__,
    summary="The Trusted Second Brain and Predictive Chief of Staff for Modern Households.",
)

# Permissive CORS for local frontend development (Vite dev server / preview).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "product": "Exhale", "version": __version__}


# --- auth endpoints -----------------------------------------------------------
class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str
    invite_code: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _session_response(user: User, token: str) -> dict:
    return {
        "token": token,
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "family_id": user.family_id,
        },
        "invite_code": auth_store.invite_code_for(user.family_id),
    }


@app.post("/v1/auth/signup")
def signup(req: SignupRequest) -> dict:
    """Create an account. Without an invite code a new family is created; with
    one, the user joins that family (the caregiver invite loop, §13.2)."""

    try:
        user, token = auth_store.signup(
            req.email, req.password, req.display_name, invite_code=req.invite_code
        )
    except (AuthError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.invite_code is None:
        store.set_profile(user.family_id, parent_first_name=req.display_name)
    return _session_response(user, token)


@app.post("/v1/auth/login")
def login(req: LoginRequest) -> dict:
    try:
        user, token = auth_store.login(req.email, req.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _session_response(user, token)


@app.post("/v1/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        auth_store.revoke_token(authorization.split(" ", 1)[1])
    return {"status": "logged_out"}


@app.get("/v1/me")
def me(user: User | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "family_id": user.family_id,
        "invite_code": auth_store.invite_code_for(user.family_id),
    }


@app.post("/v1/families/{family_id}/extractions")
def ingest_extraction(payload: ExtractionPayload, family_id: str = Depends(require_family_access)) -> dict:
    """Route an extraction through the confidence matrix and update the graph."""

    entry = store.ingest(family_id, payload)
    return {
        "extraction_id": entry.extraction_id,
        "routing": {
            "band": entry.decision.band.value,
            "status": entry.decision.status.value,
            "commits_to_graph": entry.decision.commits_to_graph,
            "requires_user_review": entry.decision.requires_user_review,
            "rationale": entry.decision.rationale,
        },
        "obligation_node_id": entry.obligation_node_id,
    }


@app.get("/v1/families/{family_id}/briefing")
def get_briefing(family_id: str = Depends(require_family_access)) -> dict:
    """Assemble the family's Weekly COO Briefing from the current graph.

    A family with no graph yet (fresh signup) gets a valid all-clear briefing,
    not an error — the empty state is a real product state.
    """

    return build_weekly_briefing(store.graph(family_id))


@app.get("/v1/families/{family_id}/ledger")
def get_ledger(family_id: str = Depends(require_family_access)) -> dict:
    """Return the extraction ledger (routing outcomes + provenance)."""

    return {"family_id": family_id, "entries": [e.to_dict() for e in store.ledger(family_id)]}


@app.get("/v1/families/{family_id}/drafts")
def get_drafts(family_id: str = Depends(require_family_access)) -> dict:
    """Layer 6 — recommended, rendered action drafts for each open gap (§6, §10)."""

    drafts = store.drafts(family_id)
    return {
        "family_id": family_id,
        "drafts": [d.model_dump(mode="json") for d in drafts],
    }


class ApproveActionRequest(BaseModel):
    obligation_node_id: str
    resolution: str = "COMPLETED"


@app.post("/v1/families/{family_id}/actions/approve")
def approve_action(req: ApproveActionRequest, family_id: str = Depends(require_family_access)) -> dict:
    """Execute an approved draft: resolve its obligation in the graph (§6)."""

    try:
        store.approve_action(
            family_id, req.obligation_node_id, resolution=req.resolution
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "family_id": family_id,
        "obligation_node_id": req.obligation_node_id,
        "stage": "EXECUTED",
        "resolution": req.resolution,
    }


class RawMessageIn(BaseModel):
    """A raw, unstructured item pushed in from a Layer 1 connector/agent."""

    source_id: str
    channel: str = "upload"
    subject: str = ""
    body: str = ""
    received_at: datetime | None = None
    sender: str | None = None
    sender_domain: str | None = None
    attachment_text: str | None = None


class ScanRequest(BaseModel):
    """Batch of raw messages to run through the 6-month retro scan (§6)."""

    messages: list[RawMessageIn]
    known_children: list[str] = Field(default_factory=list)
    days: int = 180


def _to_raw(msg: RawMessageIn) -> RawMessage:
    from exhale.connectors.base import Attachment

    attachments = ()
    if msg.attachment_text:
        attachments = (Attachment(filename="attachment", mime_type="text/plain",
                                  text=msg.attachment_text),)
    return RawMessage(
        source_id=msg.source_id,
        channel=msg.channel,
        subject=msg.subject,
        body=msg.body,
        received_at=msg.received_at or datetime.now(timezone.utc),
        sender=msg.sender,
        sender_domain=msg.sender_domain,
        attachments=attachments,
    )


@app.post("/v1/families/{family_id}/scan")
def scan_household(req: ScanRequest, family_id: str = Depends(require_family_access)) -> dict:
    """Run raw connector messages through extract → route → graph, return a
    Household Assessment Snapshot (Blueprint §3, §6)."""

    connector = FixtureConnector(_to_raw(m) for m in req.messages)
    ctx = ExtractionContext(known_children=req.known_children)
    result = run_retro_scan(
        connector, store, family_id, ctx, days=req.days, extractor=pipeline_extractor
    )
    return {
        "family_id": family_id,
        "scanned": result.scanned,
        "extracted": result.extracted,
        "committed": result.committed,
        "pending": result.pending,
        "rejected": result.rejected,
        "snapshot": result.snapshot,
    }


class GmailSyncRequest(BaseModel):
    known_children: list[str] = Field(default_factory=list)


def _gmail_connector_from_env():
    """Build a GmailConnector from environment credentials, or ``None``.

    Either ``EXHALE_GMAIL_ACCESS_TOKEN``, or the OAuth refresh trio
    ``EXHALE_GMAIL_REFRESH_TOKEN`` + ``EXHALE_GMAIL_CLIENT_ID`` +
    ``EXHALE_GMAIL_CLIENT_SECRET``.
    """

    import os

    access = os.environ.get("EXHALE_GMAIL_ACCESS_TOKEN")
    refresh = os.environ.get("EXHALE_GMAIL_REFRESH_TOKEN")
    if not access and not refresh:
        return None
    from exhale.connectors.gmail import GmailConnector

    return GmailConnector(
        access_token=access,
        refresh_token=refresh,
        client_id=os.environ.get("EXHALE_GMAIL_CLIENT_ID"),
        client_secret=os.environ.get("EXHALE_GMAIL_CLIENT_SECRET"),
    )


@app.post("/v1/families/{family_id}/sync/gmail")
def sync_gmail(req: GmailSyncRequest, family_id: str = Depends(require_family_access)) -> dict:
    """Pull new Gmail messages through extract → route → graph (§1, §2 Layer 1).

    Incremental: only messages since the last sync (watermark persisted in the
    family profile); first run covers the 180-day retro window.
    """

    connector = _gmail_connector_from_env()
    if connector is None:
        raise HTTPException(
            status_code=503,
            detail="Gmail is not configured. Set EXHALE_GMAIL_ACCESS_TOKEN, or "
                   "EXHALE_GMAIL_REFRESH_TOKEN + EXHALE_GMAIL_CLIENT_ID + "
                   "EXHALE_GMAIL_CLIENT_SECRET.",
        )
    ctx = ExtractionContext(known_children=req.known_children)
    result = run_incremental_sync(
        connector, store, family_id, ctx, extractor=pipeline_extractor
    )
    return {
        "family_id": family_id,
        "scanned": result.scanned,
        "extracted": result.extracted,
        "committed": result.committed,
        "pending": result.pending,
        "rejected": result.rejected,
        "snapshot": result.snapshot,
    }


@app.get("/v1/demo/briefing")
def demo_briefing() -> dict:
    """Convenience alias: the seeded demo household's briefing."""

    return build_weekly_briefing(store.graph(DEMO_FAMILY_ID))
