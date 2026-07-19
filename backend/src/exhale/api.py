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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from exhale import __version__
from exhale.briefing import build_weekly_briefing
from exhale.connectors.base import RawMessage
from exhale.connectors.memory import FixtureConnector
from exhale.extraction import ExtractionContext
from exhale.retro_scan import run_retro_scan
from exhale.schemas import ExtractionPayload
from exhale.seed import DEMO_FAMILY_ID, seed_demo
from exhale.store import HouseholdStore

store = HouseholdStore()
seed_demo(store)
store.set_profile(DEMO_FAMILY_ID, parent_first_name="Andrew")

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


@app.post("/v1/families/{family_id}/extractions")
def ingest_extraction(family_id: str, payload: ExtractionPayload) -> dict:
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
def get_briefing(family_id: str) -> dict:
    """Assemble the family's Weekly COO Briefing from the current graph."""

    graph = store.graph(family_id)
    if not graph.nodes:
        raise HTTPException(status_code=404, detail=f"No graph for family {family_id!r}")
    return build_weekly_briefing(graph)


@app.get("/v1/families/{family_id}/ledger")
def get_ledger(family_id: str) -> dict:
    """Return the extraction ledger (routing outcomes + provenance)."""

    return {"family_id": family_id, "entries": [e.to_dict() for e in store.ledger(family_id)]}


@app.get("/v1/families/{family_id}/drafts")
def get_drafts(family_id: str) -> dict:
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
def approve_action(family_id: str, req: ApproveActionRequest) -> dict:
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
def scan_household(family_id: str, req: ScanRequest) -> dict:
    """Run raw connector messages through extract → route → graph, return a
    Household Assessment Snapshot (Blueprint §3, §6)."""

    connector = FixtureConnector(_to_raw(m) for m in req.messages)
    ctx = ExtractionContext(known_children=req.known_children)
    result = run_retro_scan(connector, store, family_id, ctx, days=req.days)
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
