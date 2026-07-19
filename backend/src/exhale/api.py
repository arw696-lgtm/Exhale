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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from exhale import __version__
from exhale.briefing import build_weekly_briefing
from exhale.schemas import ExtractionPayload
from exhale.seed import DEMO_FAMILY_ID, seed_demo
from exhale.store import HouseholdStore

store = HouseholdStore()
seed_demo(store)

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


@app.get("/v1/demo/briefing")
def demo_briefing() -> dict:
    """Convenience alias: the seeded demo household's briefing."""

    return build_weekly_briefing(store.graph(DEMO_FAMILY_ID))
