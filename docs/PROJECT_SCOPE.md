# Exhale — Full Project Scope & Status

*As of 2026-07-22 · 24 PRs merged · 431 tests (423 always-on + 8 Postgres-gated) · repo `arw696-lgtm/Exhale`*

This is the complete map of the project: what Exhale is, what has been built,
the design laws it runs on, and — most importantly for gap analysis — an honest
register of everything **not** built, deferred, or waiting on external work.

---

## 1. Vision

**Exhale is a shared brain for the household** — the same institutional memory
and operational continuity a corporation buys, applied to a family. Reactive
tools store what you type; Exhale *reasons*: it discovers obligations in the
household's own information streams, predicts what they require, watches for
the gaps nobody wrote down (who has the child Saturday night?), asks when it
isn't sure, learns the family's rhythms, and — with permission — acts.

The founding constraint, learned from live failures on real family data:
**a household brain that guesses loses trust and dies.** Every subsystem is
therefore built on the credibility discipline (see §4).

### 1.1 The second-family thesis

In the founder's words:

> I was a pretty functional adult for a long time — I got married later in
> life, had a child later in life. Then add a wife, a child, a house, a dog,
> and all the responsibilities that come with them, and life got genuinely
> hard to manage. There are people I want to connect with and I can't find
> the time. I want to exercise. I want to be a great parent, a great
> financial planner — most of all a great husband. I need help finding time.
> Ali needs help finding time — for doctor's appointments, for exercise, to
> go get a facial, to do the things that are good for all of us. If this
> product can help us do that, then I know a lot of other families it could
> maybe help too. Exhale is exactly what it's meant to be: **a breath for
> people.**
>
> — Andy Ward, founder

The engineering corollary: the bet is that "help us find time" is
family-shaped, not Ward-shaped. The overload Andy describes — obligations
arriving faster than anyone can track, care gaps nobody wrote down, two
adults who can't see where their own hours went — is the modern-household
default, and what's genuinely specific to this house lives in configuration
(the coverage model, learned rules, connected calendars), not in code. Every
design law in §4 was forced by a live failure on this family's actual data —
evidence no synthetic test set produces. The honest qualifier stands: the
thesis is **untested until a second family runs it**, and the gate is
deliberate — §5C (security audit, invite-only signup, hosting, Google
verification) must clear before a family we don't share a dinner table with
is invited in. Until then, "not yet" stays the answer — a family tool being
run hard enough to earn the right to be a product.

## 2. Architecture (blueprint v2.0, six layers + cross-cutting)

| Layer | Role | Implementation |
|---|---|---|
| 1 · Data Collection | Pull household info from its real channels | `connectors/` (gmail, gcal, msgraph, ics), vision photos, auto-sync |
| 2 · Extraction | Unstructured → validated structured facts | `extraction.py`, `extraction_llm.py`, `extraction_vision.py`, `credibility.py`, `routing.py` |
| 3 · Knowledge Graph | Typed entities & relationships, encrypted | `graph.py`, `store.py`, `persistence.py`, `secure.py`, `sql/schema.sql` |
| 4 · Memory | Learned patterns & open loops | `memory.py`, `waiting.py` |
| 5 · Prediction | Forward-looking risk & opportunity | `forgetting_engine.py`, `coverage.py` (care gaps + work windows) |
| 6 · Action | Suggest → draft → execute with permission | `actions.py`, `templates.py`, `autonomy.py`, calendar write |
| Security | Zero-knowledge storage, family isolation | `crypto.py`, `secure.py`, `auth.py`, `oauth.py` |
| Product | Multi-user app: signup → connect → live | FastAPI `api.py`, React frontend, OAuth flows |

## 3. What Is Built (complete inventory)

### 3.1 Data collection (Layer 1)
- **Gmail** — live REST connector, OAuth w/ refresh, incremental sync via a
  persisted watermark; first run covers a 180-day retro window.
- **Google Calendar** — reads busy blocks (recurrences expanded server-side);
  Free-marked / all-day / cancelled events correctly do **not** block.
- **Outlook / Office 365** — Microsoft Graph `calendarView`, same discipline.
- **`.ics` universal path** — any published calendar URL (iCloud shared,
  Outlook, Google secret address) with client-side RRULE expansion
  (DAILY/WEEKLY/MONTHLY, INTERVAL, COUNT, UNTIL, weekly BYDAY); plus direct
  **file upload** (no hosting needed).
- **Photos & screenshots** — Claude vision reads flyers, confirmations, app
  screenshots into the same pipeline; a dedicated grade-aware path reads a
  **school-calendar image** straight into the coverage model's no-school days.
- **Background auto-sync** — a daemon (env-gated) replays each family's
  remembered syncs on a schedule with per-unit failure isolation.

### 3.2 Extraction & credibility (Layer 2)
- **Deterministic engine** — regex + dateutil + heuristics; relative dates
  resolve on the *message's* timeline; time-window extraction is range-only
  (never turns a pickup cutoff into a start time).
- **LLM hybrid** — Claude with structured outputs reads what heuristics can't;
  HIGH-confidence deterministic results never cost an API call; API failure
  degrades gracefully.
- **Vision extraction** — same contract from images; multiple items per image.
- **Credibility layer** (the trust core):
  - Artifact tiers `CONFIRMATION > LOGISTICS > REMINDER > NEWSLETTER > MARKETING`;
  - `FactOrigin` OBSERVED / INFERRED / USER_CONFIRMED on every date;
  - Routing ceilings (reminders & inferred dates never auto-commit; marketing
    always rejected) and a floor (a confirmation-tier observed fact is never
    silently dropped for a low heuristic score);
  - `missing_fields` — unknown values are a named state, never a default;
  - Corroboration — witness counts per event anchor;
  - Coverage statements — every briefing names connected sources *and* known
    blind spots.
- **Confidence routing** (§3.3): HIGH ≥0.92 commit · 0.70–0.91 pending review
  · <0.70 reject.

### 3.3 Knowledge graph & storage (Layer 3)
- Typed nodes (PERSON, ORGANIZATION, EVENT, DOCUMENT, OBLIGATION) and edges
  (DEPENDS_ON, ENROLLED_IN, …) with traversal helpers.
- **Encrypted-at-rest Postgres persistence**: per-family KEK (PBKDF2 from a
  master secret + per-family salt), AES-GCM envelope per payload, blind
  indexes; the DB holds ciphertext + topology only. In-memory store for dev.
- Extraction ledger with full provenance; corrections supersede (audit kept).

### 3.4 Memory (Layer 4)
- **Learned rules** — deterministic pattern mining over the ledger: weekly
  cadences ("ISLA Camp recurs on Mondays") and deadline leads ("registration
  closes 5 days before — always a Wednesday"). Multi-witness required,
  inconsistent samples never averaged, resends deduped, evidence cited.
- **Waiting-On ledger** — open loops where someone owes the family a reply;
  staleness-stratified (week = nudge, two weeks = critical); resolve ≠ erase.

### 3.5 Prediction (Layer 5)
- **Forgetting Engine** — dependency-chain risk scoring
  (`Risk = P_forget × Impact`), stratified 🔴 ≤36h / 🟡 ≤14d / 🔵 beyond.
- **Care-Coverage Engine** — the supervision floor: subtracts school, camps,
  care programs, and each caregiver's availability (work patterns *inferred*,
  calendar events *observed*) from the child's supervised window; what remains
  is a care gap, provenance-flagged (`depends_on_inference`).
- **Work windows** — the intent side of the same math: when a caregiver is
  free *and* the child is covered; ranked suggestions ("3 best blocks this
  week"); drop-off/pickup pinches correctly excluded.

### 3.6 Action & autonomy (Layer 6)
- **Action drafts** — each dependency gap renders an approvable draft
  (sign form / request record / …); approval resolves the obligation.
- **Calendar write** — `create_event` on Google + Outlook (events only, never
  calendar management); `POST /schedule` with provider auto-selection; the
  **published Exhale `.ics` feed** as the zero-OAuth path to phone/CarPlay.
- **Controlled autonomy** — per-household dial per action category
  (OFF / ASK / AUTO, default ASK; the human tap is the approval), plus an
  **earned-trust record**: review-queue decisions score Exhale's judgment;
  `eligible_for_auto` only at ≥10 decisions & ≥90% accuracy; promotion is
  *proposed*, only a human flips the dial.

### 3.7 Security & multi-tenancy
- Zero-knowledge storage (see 3.3); passwords PBKDF2-600k; session tokens
  stored as SHA-256 hashes; every family route family-scoped (cross-family →
  403); invite codes for spouses/caregivers.
- **Multi-user OAuth** ("Connect Google/Outlook"): one developer app per
  provider, per-family tokens encrypted at rest, HMAC-signed `state` binding
  each flow to its family (forgery/expiry/replay rejected). Read-only scopes
  plus events-write only.
- Feed URLs are secret-token credentials (per family, minted once).

### 3.8 Product surface (frontend + API)
- **Weekly COO Briefing** — critical threats, dependency watch, Care Watch,
  Waiting-On, learned patterns, coverage statement, all-clear state.
- **Review queue** — everything held PENDING_VERIFICATION with *why it was
  held*; one-tap Confirm (→ USER_CONFIRMED ground truth) / Dismiss (kept as
  signal).
- **Setup form** — two-minute household onboarding (child, caregivers, work
  patterns, school) replacing raw JSON.
- **Photo drop, work-windows panel, Connections panel** (both connect buttons
  + feed link), **Add-to-calendar** on work windows *and* care gaps.
- ~30 REST endpoints (see README table); auth-gated; CI: pytest + vite build.

### 3.9 Added since the first edition of this document (PRs #14–#23)
- **Full-code bug hunt** — seven reproduced-then-fixed defects (tz-mixed
  scheduling 500, month-end RRULE crash, invalid ICS output, duplicate
  confirms/photos/scans, elapsed-time work windows) + feed-token hardening.
- **Outbound notifications** (`notify.py`) — 🔴 items emailed, one digest per
  cycle, each alert exactly once; runs with auto-sync; per-family opt-in.
- **Why-traces** — every briefing item expands to its provenance (source
  document, tier, observed/inferred, named unknowns).
- **Signup lockdown** — invite-only flag + bootstrap code; per-IP rate
  limiting on auth/OAuth surfaces.
- **Family-structure work** (see `FAMILY_STRUCTURES.md`) — role-flexible
  caregivers; the **HELPER** tier (weekday-scoped invites, default-deny
  enforcement, provenance-free sharing — the §3.3 seam).
- **Multi-child coverage** — N children over shared caregivers; gaps merge
  per child, work windows intersect (free only when *every* child is
  covered); legacy profiles normalize automatically.
- **Birthdates** (`ages.py`) — aging-out prompts, sibling-sitter
  suggestions, grade inference; asks only, never decisions; encryption
  pinned by a live-Postgres no-plaintext test.
- **Founder's thesis** (§1.1) + **time-back language pass** across the
  product surface ("Find Your Time", day-specific confirmations, honest
  two-state all-clear).
- **"What Exhale Handled This Week"** (`handled.py`) — resolved-items log
  (hooks at existing resolution points only), relief-toned closing recap,
  and the quiet-week distinction (zero resolved + open 🔴/🟡 never reads
  as calm).
- **Personal intentions → "Time For What Matters"** (`intentions.py`) —
  a 30-second input laid next to the engine's real windows (human decides,
  no auto-assignment), anti-guilt staleness (4-week check-in → reconfirm /
  let go / auto-stale), one matched-window follow-up ("did that happen?" —
  the thesis's only measurement point; stored, not yet aggregated), and a
  nudge that shows once, never weekly.

### 3.10 Validation performed on real data
- Retro-scan and live searches over the founder's actual Gmail surfaced real
  obligations (camps, forms, reschedules) and exposed the failure modes that
  produced the credibility layer.
- Coverage engine reproduced the household's real week (camp block split
  around an actual study block; evenings as work windows) from live calendar
  data; the two real shared-calendar concerts generate sitter gaps end-to-end.

## 4. Design laws (non-negotiables baked into code)

1. **Cite or confess** — every fact carries provenance; unknown is a named
   state, never a plausible default.
2. **Inferred ≠ observed** — a hard type distinction that routing enforces;
   inferred facts never auto-commit.
3. **Low-tier artifacts don't establish facts** — reminders reference,
   confirmations establish; marketing never does.
4. **Coverage honesty** — the brain always knows (and says) what it *cannot*
   see.
5. **Corrections are gold** — user fixes become top-tier ground truth and a
   logged failure signal; nothing is silently erased.
6. **Autonomy is earned, never self-granted** — dials per household; evidence-
   based promotion proposals; humans flip the switch.
7. **Act at the threshold, not over it** — Exhale reduces friction to zero and
   stops where money/identity/judgment begins (no purchasing).
8. **One family's failure never stalls another** — background work is
   isolation-first.

## 5. Gap register (for analysis — known, honest, prioritized)

### A. Functional gaps (product would feel these)
| Gap | Notes |
|---|---|
| ~~No notification/push channel~~ **Closed** | Email alerts for 🔴 items shipped (`notify.py`): alert-once keys, one digest per cycle, runs with auto-sync. SMS/push remain unbuilt. |
| ~~Single-child coverage model~~ **Closed** | Any number of children: per-child engines (own school/hours/programs) over shared caregivers via `FamilyCoverage`. Gaps merge per child; work windows intersect (a caregiver is free only when *every* child is covered). Legacy single-child profiles normalize automatically. Optional per-child **birthdate** (`ages.py`) powers aging-out prompts, sibling-sitter suggestions, and grade inference — asks only, never decisions. |
| **No edit/delete for scheduled events** | Calendar write is create-only; no two-way sync (moving/cancelling an Exhale-written event isn't tracked). |
| **Email thread / conversation state** | Extraction treats messages independently; a reschedule thread isn't linked into one evolving obligation (partially mitigated by anchors + corroboration). |
| **Coverage-model editing UI** | The setup form creates; there is no UI to *edit* an existing model (re-running setup or API only). |
| ~~Work-pattern flexibility~~ **Closed** | Setup UI now takes any weekday combination (shift/weekend schedules); truly irregular week-to-week hours still come from calendar sync. |
| **Care programs (e.g. Aventuras) have no UI** | API-only; no form to enter non-school-day care dates. |
| **Recurring event writes** | `/schedule` writes single events only (no RRULE creation). |
| **Timezone is effectively single-household** | `America/Chicago` defaults in several places; fine for the founding family, not multi-region ready. |
| **Family-structure assumptions** | Two of four structures now built: scoped caregiver access (**HELPER** role — per-weekday care visibility + explicitly shared items, default-deny enforced) and non-parent role flexibility. Partitioned visibility for co-parenting across households (§3.3) remains the hard case — named, sequenced, and seam-laid (provenance-free shared summaries) in **docs/FAMILY_STRUCTURES.md**. Open: graceful low-witness corroboration; per-child/per-obligation granularity. |

### B. Connections not built (deliberate deferrals)
| Item | Status |
|---|---|
| **CalDAV** (personal iCloud/Fastmail direct) | Deferred by choice; `.ics` publish covers most cases read-only. Cheap to add later (parser exists). |
| **ParentSquare native** | No public API exists; covered via photo ingestion + email digests by design. |
| **Outlook/Graph *mail* ingestion** | Graph calendar is built; Mail.Read scope is requested but no Graph mail connector yet (Gmail only). |
| **SMS/voice ingestion** | Not started. |

### C. Trust/scale/operations (before real users beyond the founding family)
| Item | Notes |
|---|---|
| **Deployment** | Nothing hosted. Deploy pack (HTTPS via Caddy, backups, guide) designed but unbuilt — parked pending decision. |
| **Google restricted-scope verification** | Gmail scope requires Google's security review (CASA) to exceed ~100 test users; Calendar is lighter. Company-level, one-time. |
| **Security audit** | Well-tested, never audited. Fine for the founding family; required before strangers. |
| **Client-side key custody** | KEKs derive from a server master secret; true device-held keys are a designed-for swap (§5.1) not yet done. |
| ~~Open signup~~ **Closed** | `EXHALE_INVITE_ONLY=1` requires an invite code; `EXHALE_BOOTSTRAP_INVITE` lets the operator mint new families. |
| ~~Rate limiting~~ **Basic** | Per-IP sliding-window limit on auth/OAuth endpoints (`EXHALE_RATE_LIMIT_PER_MINUTE`, in-memory, single-process). Broader abuse controls (captcha, lockout, per-account limits) unbuilt. |
| ~~OAuth connection displacement~~ **Closed** | Connections are keyed per member (`connections.py`): a second parent connecting Gmail adds their account alongside the first — every sync path iterates all grants, each inbox on its own watermark. Remaining member-level singletons (deliberate, small): one `notify_email` per family; drafts greet the founding member. |
| **Backups / disaster recovery** | Nothing automated. |
| **Ledger growth** | Append-only with full-graph rewrite persistence; fine at family scale, needs upsert strategy at scale. |
| **Observability** | Logs only; no metrics/alerting. |

### D. Founder-side tasks (config, not code — everything is waiting on these)
1. Google Cloud OAuth app registration (~1 hr, once) → 3 env vars.
2. Microsoft/Azure app registration (when Outlook matters) → 3 env vars.
3. Ali publishes the shared iCloud calendar → paste link into `/sync/ics`.
4. `ANTHROPIC_API_KEY` in `.env` → photos + LLM extraction go live.
5. Hosting decision → deploy pack build → one evening + ~$10/month.

## 6. Suggested priority order for the next phase

1. ~~**Notifications**~~ Done — email alerts shipped; SMS/push when demand appears.
2. **Deploy pack + hosting** (everything else compounds once it's live).
3. ~~**Scoped caregiver access**~~ Done — HELPER role shipped (FAMILY_STRUCTURES
   §3.2); §3.3 partitioned visibility is the next structural step when a real
   co-parenting household needs it.
4. ~~**Multi-child coverage**~~ Done — N children, merged gaps, intersected
   work windows.
5. **Founder config tasks** (interleaved — each one lights up a built system).
6. **Thread/conversation state** (the last big extraction-quality item).
7. Coverage-model edit UI · recurring writes · CalDAV — as demand appears.

---

*Everything in §3 is merged to `main`, CI-green, and covered by the test
suite. Everything in §5 is a conscious, recorded absence — the same
cite-or-confess rule the product runs on, applied to the project itself.*
