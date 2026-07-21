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

from datetime import date, datetime, time, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from exhale import __version__
from exhale.auth import AuthError, InMemoryAuthStore, User
from exhale.briefing import build_weekly_briefing
from exhale.connectors.base import RawMessage
from exhale.connectors.memory import FixtureConnector
from exhale.coverage import build_care_watch
from exhale.coverage_config import CoverageModelIn, build_engine, default_range
from exhale.credibility import build_coverage
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


def _oauth_state_secret() -> str:
    """Server-side secret for signing OAuth ``state`` tokens."""

    import os

    return os.environ.get("EXHALE_MASTER_SECRET") or "exhale-dev-oauth-state-secret"


def _family_tokens(family_id: str, provider: str) -> dict | None:
    """The family's stored OAuth tokens for ``provider`` (from a "Connect …" flow)."""

    conns = store.profile(family_id).get("connections") or {}
    tokens = conns.get(provider)
    if tokens and (tokens.get("refresh_token") or tokens.get("access_token")):
        return tokens
    return None


def _family_google_tokens(family_id: str) -> dict | None:
    tokens = _family_tokens(family_id, "google")
    if tokens:
        return tokens
    return None


def _remember_sync(family_id: str, kind: str, config: dict) -> None:
    """Persist a successful sync's parameters so auto-sync can replay them.

    ``ics`` configs accumulate as a list (deduped by url+holder); ``gcal`` and
    ``outlook`` keep the latest single config.
    """

    configs = dict(store.profile(family_id).get("sync_configs") or {})
    if kind == "ics":
        existing = [c for c in (configs.get("ics") or [])
                    if not (c.get("url") == config.get("url")
                            and c.get("holder") == config.get("holder"))]
        configs["ics"] = existing + [config]
    else:
        configs[kind] = config
    store.set_profile(family_id, sync_configs=configs)


store = _build_store()
auth_store = _build_auth_store()
pipeline_extractor = _build_extractor()
# Background auto-sync (off unless EXHALE_AUTO_SYNC_MINUTES is set).
from exhale.auto_sync import scheduler_from_env  # noqa: E402

auto_sync_scheduler = scheduler_from_env(store, pipeline_extractor)
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


# --- OAuth ("Connect Google" / "Connect Outlook") -----------------------------------
_CONNECTABLE = {"google", "microsoft"}


def _merge_connection(family_id: str, provider: str, record: dict) -> None:
    conns = dict(store.profile(family_id).get("connections") or {})
    conns[provider] = record
    store.set_profile(family_id, connections=conns)


def _start_connect(provider: str, family_id: str) -> dict:
    from exhale.oauth import authorization_url, config_from_env

    config = config_from_env(provider)
    if config is None:
        raise HTTPException(
            status_code=503,
            detail=f"{provider.title()} OAuth is not configured (developer step).",
        )
    return {"authorization_url": authorization_url(config, family_id, _oauth_state_secret())}


def _handle_callback(provider: str, code: str, state: str) -> dict:
    from datetime import datetime, timezone

    from exhale.oauth import OAuthStateError, config_from_env, exchange_code, verify_state

    config = config_from_env(provider)
    if config is None:
        raise HTTPException(status_code=503, detail=f"{provider.title()} OAuth is not configured.")
    try:
        family_id = verify_state(state, _oauth_state_secret())
    except OAuthStateError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid state: {exc}") from exc
    try:
        tokens = exchange_code(config, code)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}") from exc

    _merge_connection(family_id, provider, {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "scope": tokens.get("scope", ""),
        "connected_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "connected", "provider": provider, "family_id": family_id}


@app.get("/v1/families/{family_id}/connect/google")
def connect_google(family_id: str = Depends(require_family_access)) -> dict:
    """Start the Google connection: returns the consent URL the button opens."""
    return _start_connect("google", family_id)


@app.get("/v1/families/{family_id}/connect/microsoft")
def connect_microsoft(family_id: str = Depends(require_family_access)) -> dict:
    """Start the Outlook/Microsoft connection: returns the consent URL."""
    return _start_connect("microsoft", family_id)


@app.get("/v1/oauth/google/callback")
def google_callback(code: str = Query(...), state: str = Query(...)) -> dict:
    """Google redirects here after consent — identity comes from the signed state."""
    return _handle_callback("google", code, state)


@app.get("/v1/oauth/microsoft/callback")
def microsoft_callback(code: str = Query(...), state: str = Query(...)) -> dict:
    """Microsoft redirects here after consent."""
    return _handle_callback("microsoft", code, state)


@app.get("/v1/families/{family_id}/connections")
def get_connections(family_id: str = Depends(require_family_access)) -> dict:
    """What this family has connected — for the settings/onboarding UI."""

    conns = store.profile(family_id).get("connections") or {}

    def _status(provider: str) -> dict:
        rec = conns.get(provider)
        return {
            "connected": bool(rec),
            "scopes": (rec.get("scope", "").split() if rec else []),
            "connected_at": (rec.get("connected_at") if rec else None),
        }

    return {
        "family_id": family_id,
        "google": _status("google"),
        "microsoft": _status("microsoft"),
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


class PhotoExtractionRequest(BaseModel):
    """A photo/screenshot to run through vision extraction (§1–3)."""

    image_base64: str
    media_type: str = "image/png"
    source_name: str = "photo"
    known_children: list[str] = Field(default_factory=list)


def _vision_extractor():
    from exhale.extraction_vision import vision_extractor_from_env

    return vision_extractor_from_env()


@app.post("/v1/families/{family_id}/extractions/photo")
def ingest_photo(
    req: PhotoExtractionRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Extract trackable items from a photo/screenshot, then route each (§3.3).

    The "just screenshot it and add it in" path: one image can yield several
    items (a sports schedule, a multi-session camp). Each flows through the same
    routing + credibility rules as email extraction. 503 if vision isn't
    configured (no Anthropic credentials).
    """

    import hashlib

    from exhale.extraction import ExtractionContext
    from exhale.extraction_vision import VisionUnavailable

    extractor = _vision_extractor()
    if extractor is None:
        raise HTTPException(
            status_code=503,
            detail="Vision extraction is not configured. Set ANTHROPIC_API_KEY.",
        )
    digest = hashlib.sha256(req.image_base64.encode()).hexdigest()[:12]
    ctx = ExtractionContext(known_children=req.known_children)
    try:
        payloads = extractor.extract(
            req.image_base64, req.media_type,
            source_name=req.source_name, source_reference=f"photo_{digest}", ctx=ctx,
        )
    except VisionUnavailable as exc:
        raise HTTPException(status_code=422, detail=f"Could not read the image: {exc}") from exc

    results = []
    for payload in payloads:
        entry = store.ingest(family_id, payload)
        results.append({
            "extraction_id": entry.extraction_id,
            "extracted_event": payload.extracted_event,
            "event_date": payload.event_date.isoformat(),
            "band": entry.decision.band.value,
            "status": entry.decision.status.value,
            "obligation_node_id": entry.obligation_node_id,
        })
    return {"family_id": family_id, "extracted": len(results), "items": results}


class SchoolPhotoRequest(BaseModel):
    """A school-calendar image to populate the coverage model's no-school days."""

    image_base64: str
    media_type: str = "image/png"
    grade: str | None = None  # e.g. "1" — excludes closures for other grades only
    school_name: str | None = None


@app.post("/v1/families/{family_id}/coverage-model/school/photo")
def ingest_school_calendar_photo(
    req: SchoolPhotoRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Read a school-calendar photo → the coverage model's no-school days.

    Closes the loop between the photo pipeline and the Care-Coverage Engine:
    snap the school calendar and the care gaps populate themselves. Requires a
    coverage model (404) and vision credentials (503).
    """

    from exhale.extraction_vision import VisionUnavailable
    from exhale.coverage_config import SchoolCalendarIn

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    extractor = _vision_extractor()
    if extractor is None:
        raise HTTPException(
            status_code=503,
            detail="Vision extraction is not configured. Set ANTHROPIC_API_KEY.",
        )
    try:
        extraction = extractor.extract_school_calendar(
            req.image_base64, req.media_type, grade=req.grade
        )
    except VisionUnavailable as exc:
        raise HTTPException(status_code=422, detail=f"Could not read the calendar: {exc}") from exc

    if extraction.first_day is None or extraction.last_day is None:
        raise HTTPException(
            status_code=422,
            detail="Could not read the school-year start/end dates from the image.",
        )

    school = SchoolCalendarIn(
        name=req.school_name or extraction.school_name or "School",
        first_day=extraction.first_day,
        last_day=extraction.last_day,
        no_school_days={c.day: c.reason for c in extraction.no_school_days},
    )
    model = CoverageModelIn(**config)
    model = model.model_copy(update={"school": school})
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {
        "family_id": family_id,
        "school": school.name,
        "first_day": school.first_day.isoformat(),
        "last_day": school.last_day.isoformat(),
        "no_school_days": len(school.no_school_days),
    }


@app.get("/v1/families/{family_id}/briefing")
def get_briefing(family_id: str = Depends(require_family_access)) -> dict:
    """Assemble the family's Weekly COO Briefing from the current graph.

    A family with no graph yet (fresh signup) gets a valid all-clear briefing,
    not an error — the empty state is a real product state. When the household
    has configured a coverage model, the child-supervision Care Watch for the
    next two weeks rides along.
    """

    from exhale.memory import learn_rules
    from exhale.waiting import build_waiting_watch

    profile = store.profile(family_id)
    waiting_items = profile.get("waiting_on") or []
    return build_weekly_briefing(
        store.graph(family_id),
        coverage=build_coverage(profile),
        care_watch=_care_watch_for(profile),
        learned_rules=[r.to_dict() for r in learn_rules(store.ledger(family_id))],
        waiting_on=build_waiting_watch(waiting_items) if waiting_items else None,
    )


def _care_watch_for(profile: dict) -> dict | None:
    """Build the next-two-weeks Care Watch if the family configured a model."""

    config = profile.get("coverage_model")
    if not config:
        return None
    engine = build_engine(CoverageModelIn(**config))
    start, end = default_range()
    return build_care_watch(engine, start, end)


@app.get("/v1/families/{family_id}/ledger")
def get_ledger(family_id: str = Depends(require_family_access)) -> dict:
    """Return the extraction ledger (routing outcomes + provenance)."""

    return {"family_id": family_id, "entries": [e.to_dict() for e in store.ledger(family_id)]}


class CorrectionRequest(BaseModel):
    """User-supplied fixes for a previous extraction — ground truth.

    Only the provided fields change; the corrected record re-routes as
    USER_CONFIRMED (always commits) and the original entry is kept, marked
    superseded — corrections are a logged failure signal, not an erasure.
    """

    extracted_event: str | None = None
    target_person_name: str | None = None
    event_date: date | None = None
    deadline_date: date | None = None
    event_start_time: time | None = None
    event_end_time: time | None = None
    action_required: bool | None = None


@app.post("/v1/families/{family_id}/extractions/{extraction_id}/correct")
def correct_extraction(
    extraction_id: str,
    req: CorrectionRequest,
    family_id: str = Depends(require_family_access),
) -> dict:
    """Apply a user correction to a ledger entry (credibility layer)."""

    fixes = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        entry = store.correct(family_id, extraction_id, **fixes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"family_id": family_id, **entry.to_dict()}


# --- Review queue: the human side of "asks when unsure" -----------------------------
def _dismissed_ids(family_id: str) -> set[str]:
    return set(store.profile(family_id).get("dismissed_extractions") or [])


@app.get("/v1/families/{family_id}/review")
def get_review_queue(family_id: str = Depends(require_family_access)) -> dict:
    """Items held PENDING_VERIFICATION, awaiting a human yes/no/fix.

    The surface for the credibility layer's core promise: anything the pipeline
    wasn't sure enough to commit waits here instead of silently landing (or
    silently vanishing). Superseded and dismissed entries are excluded.
    """

    from exhale.routing import RecordStatus

    dismissed = _dismissed_ids(family_id)
    pending = [
        e.to_dict()
        for e in store.ledger(family_id)
        if e.decision.status is RecordStatus.PENDING_VERIFICATION
        and e.superseded_by is None
        and e.extraction_id not in dismissed
    ]
    pending.sort(key=lambda d: d["event_date"])
    return {"family_id": family_id, "count": len(pending), "pending": pending}


@app.post("/v1/families/{family_id}/extractions/{extraction_id}/confirm")
def confirm_extraction(
    extraction_id: str, family_id: str = Depends(require_family_access)
) -> dict:
    """Confirm a pending item as-is — 'yes, that's real.'

    A confirmation is a correction that changes nothing: the entry re-routes as
    USER_CONFIRMED (always commits) and the original is kept, superseded.
    """

    try:
        entry = store.correct(family_id, extraction_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"family_id": family_id, **entry.to_dict()}


@app.post("/v1/families/{family_id}/extractions/{extraction_id}/dismiss")
def dismiss_extraction(
    extraction_id: str, family_id: str = Depends(require_family_access)
) -> dict:
    """Dismiss a pending item — 'not a real obligation.'

    The entry stays in the ledger (dismissals are signal, not erasure) but drops
    out of the review queue; the dismissed set persists in the encrypted profile.
    """

    if not any(e.extraction_id == extraction_id for e in store.ledger(family_id)):
        raise HTTPException(status_code=404, detail=f"No extraction {extraction_id!r}")
    dismissed = _dismissed_ids(family_id)
    dismissed.add(extraction_id)
    store.set_profile(family_id, dismissed_extractions=sorted(dismissed))
    return {"family_id": family_id, "extraction_id": extraction_id, "status": "dismissed"}


# --- Controlled autonomy: dials, trust record, and calendar write -------------------
class AutonomyUpdate(BaseModel):
    calendar_write: str | None = None  # OFF | ASK | AUTO


@app.get("/v1/families/{family_id}/autonomy")
def get_autonomy(family_id: str = Depends(require_family_access)) -> dict:
    """The household's autonomy dials + Exhale's earned trust record."""

    from exhale.autonomy import autonomy_settings, trust_record

    profile = store.profile(family_id)
    return {
        "family_id": family_id,
        "settings": autonomy_settings(profile),
        "trust": trust_record(store.ledger(family_id), _dismissed_ids(family_id)),
    }


@app.put("/v1/families/{family_id}/autonomy")
def set_autonomy(
    req: AutonomyUpdate, family_id: str = Depends(require_family_access)
) -> dict:
    """Move a dial. Only a human calls this — Exhale never promotes itself."""

    from exhale.autonomy import AutonomyLevel, autonomy_settings

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    for key, value in updates.items():
        if value not in AutonomyLevel.__members__:
            raise HTTPException(status_code=400, detail=f"{key} must be OFF, ASK, or AUTO")
    current = dict(store.profile(family_id).get("autonomy") or {})
    current.update(updates)
    store.set_profile(family_id, autonomy=current)
    return {"family_id": family_id, "settings": autonomy_settings(store.profile(family_id))}


class ScheduleRequest(BaseModel):
    """An event to place on a family calendar (the write half of autonomy)."""

    title: str
    start: datetime
    end: datetime
    description: str = ""
    provider: str | None = None  # google | microsoft | feed; auto-picked if omitted


@app.post("/v1/families/{family_id}/schedule")
def schedule_event(
    req: ScheduleRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Write an event to the family's calendar, governed by the autonomy dial.

    OFF → refused. ASK/AUTO → written (at ASK, the human tap that triggered
    this call *is* the approval). Provider auto-selection: a connected Google
    account, else a connected Microsoft account, else the published Exhale
    feed (which the phone subscribes to — the zero-OAuth path to CarPlay).
    """

    from exhale.autonomy import AutonomyLevel, level_for

    profile = store.profile(family_id)
    if level_for(profile, "calendar_write") is AutonomyLevel.OFF:
        raise HTTPException(
            status_code=403,
            detail="Calendar writing is turned OFF for this household "
                   "(PUT /autonomy to change).",
        )
    if req.end <= req.start:
        raise HTTPException(status_code=400, detail="end must be after start")

    provider = req.provider
    if provider is None:
        if _family_tokens(family_id, "google"):
            provider = "google"
        elif _family_tokens(family_id, "microsoft"):
            provider = "microsoft"
        else:
            provider = "feed"

    start = req.start.replace(tzinfo=None)
    end = req.end.replace(tzinfo=None)
    if provider == "google":
        connector = _gcal_connector_for_family(family_id, caregiver_name="_writer",
                                               calendar_id="primary")
        if connector is None:
            raise HTTPException(status_code=503, detail="Google is not connected.")
        created = connector.create_event(req.title, start, end, description=req.description)
        ref = created.get("id", "")
    elif provider == "microsoft":
        connector = _msgraph_connector_for_family(family_id, caregiver_name="_writer")
        if connector is None:
            raise HTTPException(status_code=503, detail="Outlook is not connected.")
        created = connector.create_event(req.title, start, end, description=req.description)
        ref = created.get("id", "")
    elif provider == "feed":
        events = list(profile.get("scheduled_events") or [])
        import uuid as _uuid

        ref = f"exhale_{_uuid.uuid4().hex[:10]}"
        events.append({"uid": ref, "title": req.title, "start": start.isoformat(),
                       "end": end.isoformat(), "description": req.description})
        store.set_profile(family_id, scheduled_events=events)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider {provider!r}")

    return {"family_id": family_id, "provider": provider, "reference": ref,
            "title": req.title, "start": start.isoformat(), "end": end.isoformat()}


@app.get("/v1/families/{family_id}/feed-url")
def get_feed_url(family_id: str = Depends(require_family_access)) -> dict:
    """The family's private Exhale-calendar URL (subscribe on a phone → CarPlay).

    Token minted once per family, stored in the encrypted profile; knowing the
    URL is the credential, so treat it like a password.
    """

    import secrets

    profile = store.profile(family_id)
    token = profile.get("feed_token")
    if not token:
        token = secrets.token_urlsafe(24)
        store.set_profile(family_id, feed_token=token)
    return {"family_id": family_id,
            "path": f"/v1/feeds/{family_id}.ics?token={token}"}


@app.get("/v1/feeds/{family_id}.ics")
def serve_feed(family_id: str, token: str = Query(...)):
    """The published Exhale calendar — every event scheduled via the feed provider.

    Deliberately outside the auth guard (calendar apps can't send bearer
    tokens); the secret token in the URL is the credential.
    """

    from fastapi.responses import Response

    profile = store.profile(family_id)
    expected = profile.get("feed_token")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Bad feed token")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Exhale//Family Feed//EN",
             "X-WR-CALNAME:Exhale"]
    for ev in profile.get("scheduled_events") or []:
        start = datetime.fromisoformat(ev["start"]).strftime("%Y%m%dT%H%M%S")
        end = datetime.fromisoformat(ev["end"]).strftime("%Y%m%dT%H%M%S")
        lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"SUMMARY:{ev['title']}",
                  f"DTSTART:{start}", f"DTEND:{end}",
                  f"DESCRIPTION:{ev.get('description') or 'Added by Exhale'}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar")


# --- Waiting-On ledger: the ball is in someone else's court -------------------------
class WaitingItemIn(BaseModel):
    """Someone owes the family a response."""

    who: str
    about: str
    since: date | None = None  # defaults to today
    channel: str | None = None  # email / phone / app …


@app.get("/v1/families/{family_id}/waiting")
def get_waiting(family_id: str = Depends(require_family_access)) -> dict:
    """Open waits, staleness-stratified (a week of silence → time to nudge)."""

    from exhale.waiting import build_waiting_watch

    return {"family_id": family_id,
            **build_waiting_watch(store.profile(family_id).get("waiting_on") or [])}


@app.post("/v1/families/{family_id}/waiting")
def add_waiting(
    req: WaitingItemIn, family_id: str = Depends(require_family_access)
) -> dict:
    """Track a new wait ("Hennepin County owes us the arborist follow-up")."""

    from exhale.waiting import new_item

    items = list(store.profile(family_id).get("waiting_on") or [])
    item = new_item(req.who, req.about, since=req.since, channel=req.channel)
    items.append(item)
    store.set_profile(family_id, waiting_on=items)
    return {"family_id": family_id, **item}


@app.post("/v1/families/{family_id}/waiting/{item_id}/resolve")
def resolve_waiting(
    item_id: str, family_id: str = Depends(require_family_access)
) -> dict:
    """They responded — mark the wait resolved (kept in the record)."""

    from exhale.waiting import resolve_item

    items = list(store.profile(family_id).get("waiting_on") or [])
    try:
        items = resolve_item(items, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.set_profile(family_id, waiting_on=items)
    return {"family_id": family_id, "item_id": item_id, "status": "resolved"}


class MissingSourceIn(BaseModel):
    """A source the family knows exists but has not connected."""

    source: str
    owns: list[str] = Field(default_factory=list)


class CoverageDeclaration(BaseModel):
    """What the pipeline can and cannot see, declared per family."""

    connected_sources: list[str] = Field(default_factory=list)
    known_missing_sources: list[MissingSourceIn] = Field(default_factory=list)


@app.put("/v1/families/{family_id}/coverage")
def declare_coverage(
    req: CoverageDeclaration, family_id: str = Depends(require_family_access)
) -> dict:
    """Declare source coverage — connected channels and known blind spots.

    The resulting statement rides on every briefing so answers touching an
    uncovered domain are visibly partial instead of silently incomplete.
    """

    store.set_profile(family_id, coverage=req.model_dump())
    return build_coverage(store.profile(family_id))


@app.put("/v1/families/{family_id}/coverage-model")
def set_coverage_model(
    model: CoverageModelIn, family_id: str = Depends(require_family_access)
) -> dict:
    """Configure the household's care-coverage model (child, caregivers, school).

    Persisted (encrypted) in the family profile; the Care-Coverage Engine reads
    it to detect child-supervision gaps for the briefing and the care-gaps API.
    """

    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {
        "family_id": family_id,
        "status": "saved",
        "recipient": model.recipient.name,
        "caregivers": [c.name for c in model.caregivers],
        "school": model.school.name if model.school else None,
    }


@app.get("/v1/families/{family_id}/care-gaps")
def get_care_gaps(
    family_id: str = Depends(require_family_access),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
) -> dict:
    """Care-supervision gaps over a date range (default: next 14 days).

    Requires a coverage model (see PUT /coverage-model); 404 if none is set.
    """

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    engine = build_engine(CoverageModelIn(**config))
    default_start, default_end = default_range()
    start = from_ or default_start
    end = to or (start + (default_end - default_start))
    return build_care_watch(engine, start, end)


@app.get("/v1/families/{family_id}/work-windows")
def get_work_windows(
    family_id: str = Depends(require_family_access),
    caregiver: str = Query(...),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    count: int = Query(default=3, ge=1, le=20),
    min_hours: float = Query(default=2.0, ge=0.25),
) -> dict:
    """Suggested best work windows for a caregiver — the intent side of coverage.

    'When can I work this week?' — times the caregiver is free AND the child is
    covered by someone/something else. Requires a coverage model (404).
    """

    from exhale.coverage import build_work_plan

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    engine = build_engine(CoverageModelIn(**config))
    default_start, default_end = default_range(days=7)
    start = from_ or default_start
    end = to or (start + (default_end - default_start))
    try:
        return build_work_plan(
            engine, caregiver, start, end, count=count, min_hours=min_hours
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CalendarSyncRequest(BaseModel):
    """Sync a caregiver's Google Calendar busy blocks into the coverage model."""

    caregiver_name: str
    calendar_id: str = "primary"
    days: int = 120  # horizon to pull busy blocks for


def _gcal_connector_for_family(family_id: str, caregiver_name: str, calendar_id: str):
    """Build a GoogleCalendarConnector, preferring the family's OAuth grant.

    A family that clicked "Connect Google" uses its own stored tokens (the app's
    registered client id/secret drive the refresh). Falls back to the legacy
    single-tenant ``EXHALE_GCAL_*`` env vars, then ``None``.
    """

    import os

    from exhale.connectors.gcal import GoogleCalendarConnector
    from exhale.oauth import config_from_env

    tokens = _family_google_tokens(family_id)
    if tokens is not None:
        cfg = config_from_env("google")
        return GoogleCalendarConnector(
            caregiver_name=caregiver_name,
            calendar_id=calendar_id,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            client_id=cfg.client_id if cfg else None,
            client_secret=cfg.client_secret if cfg else None,
        )

    access = os.environ.get("EXHALE_GCAL_ACCESS_TOKEN")
    refresh = os.environ.get("EXHALE_GCAL_REFRESH_TOKEN")
    if not access and not refresh:
        return None
    return GoogleCalendarConnector(
        caregiver_name=caregiver_name,
        calendar_id=calendar_id,
        access_token=access,
        refresh_token=refresh,
        client_id=os.environ.get("EXHALE_GCAL_CLIENT_ID"),
        client_secret=os.environ.get("EXHALE_GCAL_CLIENT_SECRET"),
    )


@app.post("/v1/families/{family_id}/sync/calendar")
def sync_calendar(
    req: CalendarSyncRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Pull a caregiver's Google Calendar busy blocks into the coverage model.

    Turns that caregiver's availability from inferred into observed: synced
    events are stamped OBSERVED, so gaps built on them are high-confidence.
    Idempotent — re-syncing replaces the previous pull. Requires a configured
    coverage model (404) and Google Calendar credentials (503).
    """

    from datetime import timedelta

    from exhale.coverage_config import merge_events

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    connector = _gcal_connector_for_family(family_id, req.caregiver_name, req.calendar_id)
    if connector is None:
        raise HTTPException(
            status_code=503,
            detail="Google Calendar is not configured. Set EXHALE_GCAL_ACCESS_TOKEN, "
                   "or EXHALE_GCAL_REFRESH_TOKEN + EXHALE_GCAL_CLIENT_ID + "
                   "EXHALE_GCAL_CLIENT_SECRET.",
        )

    now = datetime.now()
    events = connector.fetch_busy(now, now + timedelta(days=req.days))
    try:
        model = merge_events(
            CoverageModelIn(**config), req.caregiver_name, events, source_prefix="gcal_"
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    _remember_sync(family_id, "gcal", {
        "caregiver_name": req.caregiver_name, "calendar_id": req.calendar_id,
        "days": req.days,
    })
    return {
        "family_id": family_id,
        "caregiver": req.caregiver_name,
        "calendar_id": req.calendar_id,
        "synced_busy_events": len(events),
    }


class ICSSyncRequest(BaseModel):
    """Sync a published .ics calendar (iCloud/Outlook shared) into the model."""

    url: str
    attendees: list[str]  # caregivers who are OUT for these events
    holder: str | None = None  # whose event bucket to store them in (default: first attendee)
    tz: str = "America/Chicago"


@app.post("/v1/families/{family_id}/sync/ics")
def sync_ics(
    req: ICSSyncRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Pull a published iCloud/Outlook shared calendar into the coverage model.

    The bridge for calendars with no clean API: the household publishes the
    shared calendar as a public .ics URL (the concerts, both-parents-out events)
    and Exhale reads it. Events are stamped with the caregivers who are out for
    them, and OBSERVED — so gaps built on them are high-confidence. Idempotent.
    """

    from exhale.connectors.ics import ICSCalendarConnector
    from exhale.coverage_config import merge_events

    if not req.attendees:
        raise HTTPException(status_code=400, detail="attendees must be non-empty")

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    holder = req.holder or req.attendees[0]
    try:
        events = ICSCalendarConnector(
            req.url, attendees=tuple(req.attendees), tz=req.tz
        ).fetch_busy()
        model = merge_events(
            CoverageModelIn(**config), holder, events, source_prefix="ics_"
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch calendar: {exc}") from exc
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    _remember_sync(family_id, "ics", {
        "url": req.url, "attendees": req.attendees, "holder": holder, "tz": req.tz,
    })
    return {
        "family_id": family_id,
        "holder": holder,
        "attendees": req.attendees,
        "synced_busy_events": len(events),
    }


class ICSUploadRequest(BaseModel):
    """Upload the contents of a `.ics` file directly (no URL/hosting needed)."""

    content: str  # the raw iCalendar text
    attendees: list[str]
    holder: str | None = None
    tz: str = "America/Chicago"


@app.post("/v1/families/{family_id}/sync/ics/upload")
def upload_ics(
    req: ICSUploadRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Import a `.ics` file's contents directly (drag-and-drop export → coverage).

    The zero-hosting path: a user exports their calendar to a file and uploads
    it, rather than publishing a public URL. Same parsing/recurrence/merge as
    the URL sync. Idempotent.
    """

    from exhale.connectors.ics import parse_ics
    from exhale.coverage_config import merge_events

    if not req.attendees:
        raise HTTPException(status_code=400, detail="attendees must be non-empty")
    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    holder = req.holder or req.attendees[0]
    events = parse_ics(req.content, tuple(req.attendees), tz=req.tz)
    try:
        model = merge_events(CoverageModelIn(**config), holder, events, source_prefix="ics_")
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {
        "family_id": family_id,
        "holder": holder,
        "attendees": req.attendees,
        "synced_busy_events": len(events),
    }


class OutlookSyncRequest(BaseModel):
    """Sync a caregiver's Outlook/Office 365 calendar busy blocks into the model."""

    caregiver_name: str
    days: int = 120


def _msgraph_connector_for_family(family_id: str, caregiver_name: str):
    """Build a GraphCalendarConnector from the family's Microsoft OAuth grant."""

    from exhale.connectors.msgraph import GraphCalendarConnector
    from exhale.oauth import config_from_env

    tokens = _family_tokens(family_id, "microsoft")
    if tokens is None:
        return None
    cfg = config_from_env("microsoft")
    return GraphCalendarConnector(
        caregiver_name=caregiver_name,
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        client_id=cfg.client_id if cfg else None,
        client_secret=cfg.client_secret if cfg else None,
    )


@app.post("/v1/families/{family_id}/sync/outlook")
def sync_outlook(
    req: OutlookSyncRequest, family_id: str = Depends(require_family_access)
) -> dict:
    """Pull a caregiver's Outlook calendar busy blocks into the coverage model.

    The Microsoft parallel to /sync/calendar (Graph calendarView expands
    recurrences server-side). Requires a coverage model (404) and a connected
    Microsoft account (503). Idempotent.
    """

    from datetime import timedelta

    from exhale.coverage_config import merge_events

    config = store.profile(family_id).get("coverage_model")
    if not config:
        raise HTTPException(
            status_code=404,
            detail="No coverage model configured. PUT /coverage-model first.",
        )
    connector = _msgraph_connector_for_family(family_id, req.caregiver_name)
    if connector is None:
        raise HTTPException(
            status_code=503,
            detail="Outlook is not connected. Use /connect/microsoft first.",
        )
    now = datetime.now()
    events = connector.fetch_busy(now, now + timedelta(days=req.days))
    try:
        model = merge_events(
            CoverageModelIn(**config), req.caregiver_name, events, source_prefix="msgraph_"
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    _remember_sync(family_id, "outlook", {
        "caregiver_name": req.caregiver_name, "days": req.days,
    })
    return {
        "family_id": family_id,
        "caregiver": req.caregiver_name,
        "synced_busy_events": len(events),
    }


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


def _gmail_connector_for_family(family_id: str):
    """Build a GmailConnector, preferring the family's OAuth grant.

    A family that clicked "Connect Google" uses its own stored tokens; falls
    back to the legacy single-tenant ``EXHALE_GMAIL_*`` env vars, then ``None``.
    """

    import os

    from exhale.connectors.gmail import GmailConnector
    from exhale.oauth import config_from_env

    tokens = _family_google_tokens(family_id)
    if tokens is not None:
        cfg = config_from_env("google")
        return GmailConnector(
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            client_id=cfg.client_id if cfg else None,
            client_secret=cfg.client_secret if cfg else None,
        )

    access = os.environ.get("EXHALE_GMAIL_ACCESS_TOKEN")
    refresh = os.environ.get("EXHALE_GMAIL_REFRESH_TOKEN")
    if not access and not refresh:
        return None
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

    connector = _gmail_connector_for_family(family_id)
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
