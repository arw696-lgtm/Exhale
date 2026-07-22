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
│   ├── tests/          pytest suite (345 tests)
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
python -m pytest             # 345 tests (incl. Postgres integration when reachable)
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
| `GET` | `/v1/families/{fid}/connect/google` · `/connect/microsoft` | start a "Connect …" OAuth flow (consent URL) |
| `GET` | `/v1/oauth/google/callback` · `/oauth/microsoft/callback` | OAuth redirect target — exchanges code, stores tokens |
| `GET` | `/v1/families/{fid}/connections` | which providers this family has connected |
| `POST` | `/v1/families/{fid}/extractions` | ingest → route (§3.3) → graph |
| `POST` | `/v1/families/{fid}/extractions/photo` | extract trackable items from a photo/screenshot → route |
| `POST` | `/v1/families/{fid}/coverage-model/school/photo` | read a school-calendar photo → coverage no-school days |
| `GET` | `/v1/families/{fid}/briefing` | Weekly COO Briefing (§9.1) |
| `GET` | `/v1/families/{fid}/review` | pending-verification queue awaiting a human yes/no |
| `POST` | `/v1/families/{fid}/extractions/{id}/confirm` · `/dismiss` | resolve a held item (confirm = USER_CONFIRMED commit) |
| `GET` | `/v1/families/{fid}/ledger` | extraction ledger + provenance |
| `GET` | `/v1/families/{fid}/drafts` | recommended action drafts (§6, §10) |
| `POST` | `/v1/families/{fid}/actions/approve` | execute a draft → resolve obligation |
| `PUT` | `/v1/families/{fid}/coverage-model` | configure the care-coverage model (child, caregivers, school) |
| `GET` | `/v1/families/{fid}/care-gaps` | child-supervision gaps over a range (Care Watch) |
| `GET` | `/v1/families/{fid}/work-windows` | a caregiver's best open work windows (intent side of coverage) |
| `GET`/`POST` | `/v1/families/{fid}/waiting` (+ `/{id}/resolve`) | Waiting-On ledger: replies someone owes the family |
| `GET`/`PUT` | `/v1/families/{fid}/autonomy` | per-household autonomy dials + earned trust record |
| `POST` | `/v1/families/{fid}/schedule` | write an event to a family calendar (Google/Outlook/feed) |
| `GET` | `/v1/families/{fid}/feed-url` → `/v1/feeds/{fid}.ics` | the published Exhale calendar (subscribe → phone/CarPlay) |
| `POST` | `/v1/families/{fid}/sync/calendar` | pull a caregiver's Google Calendar busy blocks into the model |
| `POST` | `/v1/families/{fid}/sync/outlook` | pull a caregiver's Outlook/Office 365 calendar (Microsoft Graph) |
| `POST` | `/v1/families/{fid}/sync/ics` | pull a published iCloud/Outlook/Google `.ics` feed (no OAuth) |
| `POST` | `/v1/families/{fid}/sync/ics/upload` | import a `.ics` file's contents directly (no hosting) |
| `POST` | `/v1/families/{fid}/scan` | retro-scan raw messages → snapshot (§6) |
| `POST` | `/v1/families/{fid}/sync/gmail` | pull new Gmail mail through the pipeline (§1) |
| `GET`/`PUT` | `/v1/families/{fid}/notifications` (+ `/test`, `/run`) | where 🔴 critical alerts get emailed (each exactly once) |
| `GET`/`POST` | `/v1/families/{fid}/intentions` (+ `/{id}/status`) | personal intentions — what the found time is *for* (Time For What Matters) |
| `POST`/`GET` | `/v1/families/{fid}/helper-invites` · `/helpers` (+ `PUT`/`DELETE` `/helpers/{id}`) | scoped-caregiver invites + roster (members only) |
| `GET` | `/v1/families/{fid}/helper-view` | a helper's scoped home: their care days + shared items (only view a helper may reach) |
| `POST` | `/v1/auth/signup` | create account (+ new family, or join via invite code) |
| `POST` | `/v1/auth/login` / `logout` | session tokens (opaque bearer, hashed at rest) |
| `GET` | `/v1/me` | current user + family invite code |

**Auth.** Every `/v1/families/{id}/*` route is family-scoped: a valid token for
another family gets 403. Enforcement defaults ON when a database is configured
(override with `EXHALE_REQUIRE_AUTH=0/1`); the in-memory dev mode stays open.
Passwords are PBKDF2 (600k iterations); session tokens are stored only as
SHA-256 hashes. A spouse or caregiver joins the same family by signing up with
its invite code (§13.2). For a hosted deployment set `EXHALE_INVITE_ONLY=1`:
signups then require a code (a family's own code joins it; the operator's
`EXHALE_BOOTSTRAP_INVITE` mints a new family). Auth and OAuth endpoints carry a
per-IP rate limit (`EXHALE_RATE_LIMIT_PER_MINUTE`, default 60, `0` = off).

**Scoped caregivers (helpers).** Not every family is two parents sharing
everything (see `docs/FAMILY_STRUCTURES.md`). A full member can mint a *helper*
invite for specific weekdays; whoever signs up with it joins as a **HELPER** who
sees only the care gaps on those days plus obligations the household explicitly
shares — and nothing else. Enforcement is **default-deny**: every family
endpoint except the scoped `/helper-view` returns 403 for a helper, so a new
route can't leak to them by omission. The family join code is never given to a
helper, and shared obligations reach them as provenance-free summaries
(what/who/when, never the inbox the fact came from) — the first seam of the
partitioned visibility the co-parenting case will need.

**Critical-alert email (`notify.py`).** The briefing is pull; 🔴 items also
*push*. Configure SMTP (`EXHALE_SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS`), have a
family set a notify address, and every auto-sync cycle ends by emailing each
family its **new** critical items — one digest per cycle, each alert exactly
once (sent keys persist in the encrypted profile), every line carrying its
source. No SMTP config → the feature is simply off.

**LLM extraction (optional).** Set `EXHALE_LLM_EXTRACTOR=1` (plus Anthropic API
credentials) and the pipeline upgrades to a hybrid: the deterministic engine
still handles anything it extracts at HIGH confidence for free, and Claude
(`claude-opus-4-8`, structured outputs — override with `EXHALE_LLM_MODEL`) reads
the messages the heuristics can't: prose reschedules, implicit obligations, odd
phrasings. If the API is unreachable the deterministic result stands — the
pipeline never breaks. See `src/exhale/extraction_llm.py`.

**Vision extraction (photos & screenshots).** `extraction_vision.py` sends an
image — a flyer photo, a school-calendar screenshot, a camp confirmation, a
ParentSquare post — to Claude with vision + structured output and produces the
same `ExtractionPayload` objects the text pipeline emits, so photos flow through
the identical routing (§3.3) and credibility rules. One image can yield several
items (a sports schedule, a multi-session camp), so it returns a list. Times are
extracted only when legible (else the honest `missing_fields` state), and a date
the model had to infer is flagged `INFERRED` — so it never silently auto-commits.
`POST /v1/families/{fid}/extractions/photo` (base64 image); requires
`ANTHROPIC_API_KEY` (503 otherwise). Model override: `EXHALE_VISION_MODEL`.

A second path closes the loop with the Care-Coverage Engine: `POST
/v1/families/{fid}/coverage-model/school/photo` reads a **school-calendar** image
and populates the coverage model's no-school days (grade-aware — pass `grade` so
closures for other grades only are excluded). Snap the school calendar and the
care gaps populate themselves.

**"Connect Google / Connect Outlook" (multi-provider OAuth, `oauth.py`).** The
productization seam: the developer registers **one** OAuth app per provider
(`EXHALE_GOOGLE_*`, `EXHALE_MSFT_*`), and every family then connects their own
account with a single click — no per-user setup. The flow is provider-generic
(Google + Microsoft today, any provider tomorrow); `connectors/msgraph.py` reads
Outlook/Office 365 calendars via Microsoft Graph `calendarView` (server-side
recurrence expansion), the parallel of `connectors/gcal.py`. `GET /connect/google` returns Google's consent
URL (carrying a signed, tamper-evident `state` that binds the flow to the
family); Google redirects to `GET /v1/oauth/google/callback`, which verifies the
state, exchanges the code, and stores that family's refresh token **encrypted at
rest** (the envelope pipeline). The Gmail and Calendar sync endpoints prefer a
family's own connected tokens, falling back to the single-tenant `EXHALE_GMAIL_*`
/ `EXHALE_GCAL_*` env vars. `GET /connections` reports what's linked. Read-only
scopes only. Fully testable without a real Google account (the token exchange
takes an injectable client; state signing is pure).

**Calendar write + controlled autonomy (`autonomy.py`).** The write half of the
action layer: `POST /schedule` places an event on the family's calendar —
Google or Outlook when connected (Apple's built-in account sync then carries it
to iPhone/CarPlay), else the family's **published Exhale feed** (`/feed-url` →
subscribe once on a phone; zero OAuth). Writing is governed by a per-household
**autonomy dial** per action category (`OFF / ASK / AUTO`, default ASK — the
human tap is the approval). The promotion rule: **autonomy is earned, never
self-granted.** Every review-queue decision scores Exhale's judgment
(confirmed = right, dismissed = wrong); when the record clears the bar (≥10
decisions, ≥90% right) the trust endpoint reports `eligible_for_auto` so the
UI can *propose* the upgrade — only a human flips the dial. OAuth scopes add
`calendar.events` (Google) / `Calendars.ReadWrite` (Microsoft); events only,
never calendar management.

**Layer-4 memory (`memory.py`).** The graph remembers facts; the memory engine
learns *patterns* — the implicit rhythms no single email states. Two
deterministic detectors mine the extraction ledger: **weekly cadence** ("ISLA
Camp recurs on Mondays") and **deadline lead** ("registration closes 5 days
before — always a Wednesday", the exact rule the founding household discovered
by missing it). A rule requires multiple witnesses, never averages inconsistent
samples, dedupes resends, and cites its evidence — the credibility discipline
applied to learning. Learned rules ride on every briefing.

**Waiting-On ledger (`waiting.py`).** Conversations where the ball is in
someone else's court — a promised reply that could quietly die ("the county
said they'd contact the arborist…"). Open waits stratify by silence: fresh =
🔵, a week = 🟡 time-to-nudge, two weeks = 🔴 the-thread-is-dying. Resolved
items are kept, marked — signal, not erasure.

**Review queue (the human side of "asks when unsure").** Anything the pipeline
holds at `PENDING_VERIFICATION` — a reminder-tier artifact, an inferred date —
waits in `GET /review` for a human decision instead of silently landing or
vanishing. The UI shows *why* each item was held; **Confirm** re-routes it as
`USER_CONFIRMED` ground truth (always commits), **Dismiss** drops it from the
queue while keeping the ledger record (dismissals are signal, not erasure).

**Background auto-sync (`auto_sync.py`).** Set `EXHALE_AUTO_SYNC_MINUTES` and a
daemon thread re-pulls each family's sources on that cadence: Gmail whenever a
Google account is connected (the watermark keeps it incremental), plus a replay
of every calendar/`.ics` sync the family has run once by hand (the parameters
are remembered in the encrypted profile). Every unit of work is individually
error-isolated, so one family's broken feed never stalls another's. Off by
default — dev and tests stay deterministic.

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

The **intent side** of the same math answers "when can I work this week?"
(`GET /work-windows?caregiver=…`): a caregiver's open windows are the times they
are free *and* the child is covered by someone/something else — so the school
block is workable, but the drop-off/pickup pinch (child home, no one else
covering) correctly is not. `suggest_work_windows()` ranks the longest blocks and
returns them in time order (`build_work_plan()` for the payload).

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

**Calendars with no OAuth (`connectors/ics.py`).** Any calendar that can publish
a public `.ics` URL — an **iCloud shared calendar**, **Outlook**, or even
**Google Calendar's own "secret address in iCal format"** — connects with zero
OAuth via `POST /v1/families/{fid}/sync/ics` (`url` + the caregivers who are out
for its events). A dependency-free VEVENT parser applies the same Free/all-day/
cancelled discipline as the Google connector and **expands recurring events**
(RRULE: DAILY/WEEKLY/MONTHLY with INTERVAL, COUNT, UNTIL, and weekly BYDAY) into
concrete occurrences within a forward window. This is the low-friction path for
an MVP: photos + `.ics` calendars need no developer console at all.

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
