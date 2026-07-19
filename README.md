# Exhale

**The Trusted Second Brain and Predictive Chief of Staff for Modern Households.**

Exhale is an AI-powered household operating system designed to eliminate the
invisible cognitive burden of managing family life. Rather than asking families
to remember everything, Exhale passively collects household information, builds a
private **Family Knowledge Graph**, detects implicit obligations, predicts
downstream preparation chains, and surfaces operational risks *before* they
become disruptions.

> Reactive tools: **User Remembers → Manually Enters Task → Static Reminder**
> Exhale: **System Discovers → Predicts Dependencies → Alerts → User Reviews & Acts**

This repository is the production-blueprint foundation (v2.0). It implements the
core, testable layers of the architecture.

---

## Architecture (6 Layers)

| Layer | Responsibility | In this repo |
|------|----------------|--------------|
| 6 · Action | Suggest → Draft → Execute | Briefing actions (frontend) |
| 5 · Prediction | Contextual foresight | `backend/.../forgetting_engine.py` |
| 4 · Memory | Recurring patterns & ledgers | graph properties / ledger table |
| 3 · Knowledge Graph | Entities & relationships | `backend/.../graph.py`, `db/schema.sql` |
| 2 · Extraction | Unstructured → structured JSON | `backend/.../schemas.py`, `routing.py` |
| 1 · Data Collection | Gmail, Calendar, Photos, PDFs | connectors (roadmap) |

## Repository layout

```
Exhale/
├── backend/            Python analytical core + HTTP service
│   ├── src/exhale/     schemas · routing · graph · forgetting_engine ·
│   │                   briefing · store · seed · api (FastAPI)
│   ├── tests/          pytest suite (43 tests)
│   └── examples/       end-to-end demo pipeline
├── db/
│   └── schema.sql      Zero-Knowledge encrypted storage schema (§5.3)
└── frontend/           React + Tailwind Sunday COO Briefing UI (§8, §9)
    └── src/            brand tokens · briefing components · API client
```

## Quick start

### Backend

```bash
cd backend
pip install -e ".[dev]"      # analytical core + API + test deps
python -m pytest             # 43 passing
PYTHONPATH=src python examples/demo_pipeline.py   # extraction → briefing

# Run the HTTP service (seeds a demo household at startup):
PYTHONPATH=src uvicorn exhale.api:app --reload    # http://localhost:8000
```

Key endpoints (see `src/exhale/api.py`):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | liveness |
| `POST` | `/v1/families/{fid}/extractions` | ingest → route (§3.3) → graph |
| `GET` | `/v1/families/{fid}/briefing` | Weekly COO Briefing (§9.1) |
| `GET` | `/v1/families/{fid}/ledger` | extraction ledger + provenance |

### Frontend

```bash
cd frontend
npm install
npm run dev                  # Sunday COO Briefing at localhost:5173
npm run build
```

The UI fetches a live briefing from the backend (`VITE_EXHALE_API`, default
`http://localhost:8000`) and falls back to a bundled fixture when the API is
unreachable, so it always renders.

## The analytical core

**Extraction contract (§3.2).** Every noisy input maps to a validated
`ExtractionPayload`; optional entities fail cleanly to `null` rather than being
guessed.

**Confidence routing (§3.3).**

| Band | Score | Outcome |
|------|-------|---------|
| High | ≥ 0.92 | Commit to graph, schedule tracking |
| Medium | 0.70–0.91 | `PENDING_VERIFICATION`, UI review |
| Low | < 0.70 | Rejected; request clearer artifact |

**Forgetting Engine (§7).** From a confirmed anchor event it traces
`DEPENDS_ON` chains, scoring each unresolved prerequisite:

```
Risk Score = Likelihood of Forgetting (P_f) × Impact of Forgetting (I_f)
```

and stratifies it into 🔴 CRITICAL (high-impact, ≤ 36h), 🟡 IMPORTANT
(≤ 14 days), or 🔵 ADVISORY.

## Security

Exhale operates under a **Zero-Knowledge Core**. Data is encrypted client-side
(PBKDF2-derived KEK → AES-GCM-256 DEK envelope). The persistence engine stores
only encrypted payloads, nonces, and KEK-wrapped tokens, with blind indexes for
querying. See `db/schema.sql`.

## Brand system (§8)

60% Sanctuary Navy `#1A2B4C` · 20% Sage Release `#7C9D96` ·
10% Looming Amber `#E29578` · 10% Pure Breath `#F8F9FA`.
Type: Instrument Serif (display) · Inter Tight (interface) · Plus Jakarta Sans
(micro-data). Encoded in `frontend/src/brand/tokens.js` and
`frontend/tailwind.config.js`.
