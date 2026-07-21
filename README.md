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
| 6 · Action | Suggest → Draft → Execute | `backend/.../actions.py`, `templates.py` |
| 5 · Prediction | Contextual foresight | `backend/.../forgetting_engine.py` |
| 4 · Memory | Recurring patterns & ledgers | graph properties / ledger table |
| 3 · Knowledge Graph | Entities & relationships | `backend/.../graph.py`, `persistence.py`, `sql/schema.sql` |
| 2 · Extraction | Unstructured → structured JSON | `backend/.../extraction.py`, `schemas.py`, `routing.py` |
| 1 · Data Collection | Gmail, Calendar, Photos, PDFs | `backend/.../connectors/`, `retro_scan.py` |

## Repository layout

```
Exhale/
├── backend/            Python analytical core + HTTP service
│   ├── src/exhale/     schemas · routing · graph · forgetting_engine ·
│   │                   briefing · store · seed · api (FastAPI) ·
│   │                   crypto · secure (Zero-Knowledge Core) ·
│   │                   actions · templates (Action engine) ·
│   │                   extraction · retro_scan · connectors/ (Data Collection) ·
│   │                   persistence (encrypted Postgres store) ·
│   │                   sql/schema.sql (Zero-Knowledge storage schema, §5.3)
│   ├── tests/          pytest suite (222 tests)
│   └── examples/       end-to-end demo pipeline
└── frontend/           React + Tailwind Sunday COO Briefing UI (§8, §9)
    └── src/            brand tokens · briefing components · API client
```

## Quick start

### Full stack in Docker

```bash
cp .env.example .env    # set POSTGRES_PASSWORD and EXHALE_MASTER_SECRET
docker compose up --build
# Web UI: http://localhost:8080   API: http://localhost:8000
```

Postgres + encrypted persistence + auth enforcement come up together; the web
bundle is built with `EXHALE_PUBLIC_API_URL` (set it to your machine's LAN
address to open Exhale on a phone).

### Backend

```bash
cd backend
pip install -e ".[dev]"      # analytical core + API + test deps
python -m pytest             # 222 tests (incl. Postgres integration when reachable)
PYTHONPATH=src python examples/demo_pipeline.py   # extraction → briefing

# Run the HTTP service (seeds a demo household at startup):
PYTHONPATH=src uvicorn exhale.api:app --reload    # http://localhost:8000
```

**Persistence.** Without configuration the service uses a volatile in-memory
store. Point it at Postgres and every family's graph, ledger, and profile is
persisted **encrypted at rest** (envelope encryption per §5; the database holds
only ciphertext plus graph topology) and survives restarts:

```bash
export EXHALE_DATABASE_URL="postgresql://user:pass@localhost:5432/exhale"
export EXHALE_MASTER_SECRET="a-long-random-secret"   # protects per-family keys
PYTHONPATH=src uvicorn exhale.api:app
```

The store bootstraps its own schema (`src/exhale/sql/schema.sql`) on startup.
Per-family KEKs are derived from the master secret + a per-family random salt;
swapping in true client-side key custody later only replaces the keyring.

Key endpoints (see `src/exhale/api.py`):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | liveness |
| `POST` | `/v1/families/{fid}/extractions` | ingest → route (§3.3) → graph |
| `GET` | `/v1/families/{fid}/briefing` | Weekly COO Briefing (§9.1) |
| `GET` | `/v1/families/{fid}/ledger` | extraction ledger + provenance |
| `GET` | `/v1/families/{fid}/drafts` | recommended action drafts (§6, §10) |
| `POST` | `/v1/families/{fid}/actions/approve` | execute a draft → resolve obligation |
| `PUT` | `/v1/families/{fid}/coverage-model` | configure the care-coverage model (child, caregivers, school) |
| `GET` | `/v1/families/{fid}/care-gaps` | child-supervision gaps over a range (Care Watch) |
| `POST` | `/v1/families/{fid}/sync/calendar` | pull a caregiver's Google Calendar busy blocks into the model |
| `POST` | `/v1/families/{fid}/scan` | retro-scan raw messages → snapshot (§6) |
| `POST` | `/v1/families/{fid}/sync/gmail` | pull new Gmail mail through the pipeline (§1) |
| `POST` | `/v1/auth/signup` | create account (+ new family, or join via invite code) |
| `POST` | `/v1/auth/login` / `logout` | session tokens (opaque bearer, hashed at rest) |
| `GET` | `/v1/me` | current user + family invite code |

**Auth.** Every `/v1/families/{id}/*` route is family-scoped: a valid token for
another family gets 403. Enforcement defaults ON when a database is configured
(override with `EXHALE_REQUIRE_AUTH=0/1`); the in-memory dev mode stays open.
Passwords are PBKDF2 (600k iterations); session tokens are stored only as
SHA-256 hashes. A spouse or caregiver joins the same family by signing up with
its invite code (§13.2).

**LLM extraction (optional).** Set `EXHALE_LLM_EXTRACTOR=1` (plus Anthropic API
credentials) and the pipeline upgrades to a hybrid: the deterministic engine
still handles anything it extracts at HIGH confidence for free, and Claude
(`claude-opus-4-8`, structured outputs — override with `EXHALE_LLM_MODEL`) reads
the messages the heuristics can't: prose reschedules, implicit obligations, odd
phrasings. If the API is unreachable the deterministic result stands — the
pipeline never breaks. See `src/exhale/extraction_llm.py`.

**Live Gmail.** `connectors/gmail.py` speaks the Gmail REST API directly
(OAuth: `EXHALE_GMAIL_ACCESS_TOKEN`, or `EXHALE_GMAIL_REFRESH_TOKEN` +
`EXHALE_GMAIL_CLIENT_ID` + `EXHALE_GMAIL_CLIENT_SECRET` for automatic token
renewal). Syncs are incremental: the last-sync watermark is stored in the
family profile — persisted and encrypted under the Postgres backend — so each
run only pulls what's new; the first run covers the 180-day retro window.

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

**Data collection & extraction (§2 Layer 1–2, §3).** Connectors
(`connectors/`) pull raw items from any channel and normalize them to a
channel-agnostic `RawMessage`. The extraction engine (`extraction.py`) cleanses
the text (§3.1), then derives the event, dates, deadline, responsible person,
and a calibrated confidence score using deterministic regex + `dateutil` +
keyword heuristics — designed as a drop-in interface an LLM extractor can
replace. The 6-month retro scan (`retro_scan.py`) runs this over a household's
history and emits the cold-start **Household Assessment Snapshot** (§6). Any
source — including an agent pulling real Gmail/Calendar — feeds the same
pipeline by wrapping items as `RawMessage`s.

**Extraction contract (§3.2).** Every noisy input maps to a validated
`ExtractionPayload`; optional entities fail cleanly to `null` rather than being
guessed.

**Confidence routing (§3.3).**

| Band | Score | Outcome |
|------|-------|---------|
| High | ≥ 0.92 | Commit to graph, schedule tracking |
| Medium | 0.70–0.91 | `PENDING_VERIFICATION`, UI review |
| Low | < 0.70 | Rejected; request clearer artifact |

**Credibility layer (`credibility.py`).** Born from two real extraction
failures in live testing (activity hours answered from a plausible default
instead of the confirmation email that stated them; a multi-leg trip reported
as one leg because the second booking lived in an unconnected inbox). Four
rules, enforced at the routing choke point so no extractor can bypass them:

- **Artifact hierarchy** — every source is tiered
  `CONFIRMATION > LOGISTICS > REMINDER > NEWSLETTER > MARKETING`.
  Confirmations *establish* facts; reminders/newsletters only *reference* them
  (they can never auto-commit — held `PENDING_VERIFICATION` even at a HIGH
  score); marketing establishes nothing (always rejected).
- **Observed vs. inferred** — every event date carries a `FactOrigin`. A date
  read from the artifact is `OBSERVED`; one derived from a relative phrase is
  `INFERRED` and never auto-commits. Unknown values (e.g. an activity's hours)
  stay a named `missing_fields` state — never a filled default.
- **Corroboration** — event anchors track distinct witnessing artifacts
  (`witness_refs`); an obligation attested by a single source is marked
  uncorroborated so downstream surfaces can say so.
- **Coverage honesty** — each family declares connected sources and known
  blind spots (`PUT /v1/families/{fid}/coverage`); every briefing carries the
  resulting statement, so answers touching an uncovered domain are visibly
  partial instead of silently incomplete.

User corrections are ground truth: `POST
/v1/families/{fid}/extractions/{id}/correct` re-routes the record as
`USER_CONFIRMED` (always commits, updates the obligation in place) and keeps
the superseded original as a logged failure signal.

**Forgetting Engine (§7).** From a confirmed anchor event it traces
`DEPENDS_ON` chains, scoring each unresolved prerequisite:

```
Risk Score = Likelihood of Forgetting (P_f) × Impact of Forgetting (I_f)
```

and stratifies it into 🔴 CRITICAL (high-impact, ≤ 36h), 🟡 IMPORTANT
(≤ 14 days), or 🔵 ADVISORY.

**Care-Coverage Engine (`coverage.py`).** The Forgetting Engine's forward-looking
sibling. Where that engine asks "what prep does this event need?", the Coverage
Engine asks the mirror question about a child who requires constant supervision:
*"what care does each day need, and is it assigned?"* A **care gap** — a stretch
where a supervised child has no caregiver and no institution covering them — is a
hard, safety-level obligation, and it's the base layer the schedule stands on
("when can a parent work" and "when does the child need a sitter" are the same
question from two sides). It composes:

- a **school calendar** whose operationally important part is the *no-school
  days* that flip the child from school-covered to needing care;
- **caregivers**, each unavailable during a recurring work pattern (often
  *inferred* from a stated schedule) and/or specific **calendar events** they
  attend (*observed* from a shared calendar — the thing that turns "both parents
  at a concert" into a sitter gap);
- optional **care programs** (e.g. a school's non-school-day care).

Each gap reuses the Forgetting Engine's exact threat bands (imminence drives the
band; an uncovered child is inherently high-impact) and carries the credibility
layer's provenance: a gap resting only on an *inferred* work pattern is flagged
`depends_on_inference` ("assumes Ali's usual hours"), while one built from
observed calendar events is high-confidence. `build_care_watch()` assembles the
briefing-ready payload. See it on real data:

```bash
cd backend && PYTHONPATH=src python examples/demo_coverage.py
```

**Live caregiver availability (`connectors/gcal.py`).** The Google Calendar
connector turns a caregiver's availability from *inferred* into *observed*:
`POST /v1/families/{fid}/sync/calendar` pulls their busy blocks (recurring
events expanded) and merges them into the coverage model. Only real busy time
counts — an event marked Free (`transparency: transparent`) or an all-day marker
does **not** blacked out the day, and cancelled events are skipped. Synced events
are stamped `OBSERVED`, so a care gap built on them is high-confidence rather than
assumption-dependent. Auth mirrors Gmail (`EXHALE_GCAL_ACCESS_TOKEN`, or the
`EXHALE_GCAL_REFRESH_TOKEN` + `EXHALE_GCAL_CLIENT_ID` + `EXHALE_GCAL_CLIENT_SECRET`
trio); re-syncing is idempotent.

**Action engine (§6, §10).** Each gap advances along the controlled-autonomy
path `Observe → Recommend → Draft → Execute with Approval → Autonomous`. The
engine infers the action type (sign form / request record / purchase supplies /
resolve conflict), renders the matching §10 template — a CRITICAL gap becomes a
PUSH "Critical Deadline Alarm", an IMPORTANT gap a briefing "Dependency Gap"
element — and stops at the approval gate. Approving executes the draft and
resolves the obligation in the graph, so it drops out of the next briefing. The
frontend surfaces this: the briefing's "Review & Sign Draft" button opens the
rendered draft in a modal with an approve action.

## Security — Zero-Knowledge Core (§5)

Data is encrypted **client-side** before it ever reaches the persistence engine,
which stores only ciphertext:

- **KEK derivation** — a 256-bit Key Encrypting Key from the household passphrase
  + per-family salt via PBKDF2-HMAC-SHA256 (600k iterations).
- **Envelope encryption** — each payload is sealed with a fresh ephemeral DEK
  (AES-GCM-256); the DEK is then wrapped with the KEK. The cloud sees only the
  encrypted blob, nonces, wrapped-DEK token, and auth tag.
- **Blind index** — keyed HMAC of a normalized value enables equality lookups
  without leaking plaintext; deterministic per-family, different across families.

Implemented in `backend/src/exhale/crypto.py` and bridged to the graph model in
`secure.py`; the output maps 1:1 onto `src/exhale/sql/schema.sql`. See it end-to-end:

```bash
cd backend && PYTHONPATH=src python examples/demo_zero_knowledge.py
```

Round-trip, tamper detection (`InvalidTag`), wrong-key rejection, and blind-index
determinism are covered by `tests/test_crypto.py` and `tests/test_secure.py`.

## Brand system (§8)

60% Sanctuary Navy `#1A2B4C` · 20% Sage Release `#7C9D96` ·
10% Looming Amber `#E29578` · 10% Pure Breath `#F8F9FA`.
Type: Instrument Serif (display) · Inter Tight (interface) · Plus Jakarta Sans
(micro-data). Encoded in `frontend/src/brand/tokens.js` and
`frontend/tailwind.config.js`.
