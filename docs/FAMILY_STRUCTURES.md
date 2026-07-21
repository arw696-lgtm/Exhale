# Exhale — Family Structure Inclusivity: Design Addendum

*A deliberate, recorded design decision, in the spirit of §5 of the project
scope — an honest register of what the current architecture assumes, and
what needs to change to serve family structures beyond the founding
household.*

---

## 1. The current assumption

The architecture as built assumes a two-parent household with shared,
mutual visibility: both adults see all data, corroboration draws on both
as witnesses, and the invite-code system treats "spouse/caregiver" as a
single category. This is not a flaw — it's the correct scope for a
founding-family prototype — but it is an assumption, and assumptions
should be named rather than left implicit.

## 2. Why this matters now

Exhale's core value proposition — a shared brain that reasons about
household obligations — depends on trust. Trust depends on the system
correctly modeling *who* should see *what*, not just *what* is true.
A household brain that shows the wrong person the wrong fact fails the
same "guesses lose trust" law that governs every other subsystem
(§4, design law 1: cite or confess).

## 3. Target family structures (in priority order)

Four structures were selected not for demographic frequency but for
architectural distinctness — each stresses a different part of the
permission and corroboration model.

### 3.1 Two-parent household, shared everything
**Status: built.** Both adults have full mutual visibility. Corroboration
uses both as witnesses. This remains the default case.

### 3.2 Single parent with a regular secondary caregiver
*(grandparent, aunt, close friend, regular sitter)*

One primary decision-maker; one or more people with partial, defined
access — e.g. visibility into Tuesday/Thursday pickup only, not the full
household picture.

**What this requires:**
- A caregiver access tier below "full household visibility" — scoped to
  specific obligations, days, or children rather than all-or-nothing
- Corroboration logic that works with fewer default witnesses: fewer
  sources should lower confidence gracefully, not be treated as an
  anomaly or a missing-data error
- This is the **highest-priority build target** — cleanly scoped,
  broadly applicable, and a natural extension of the existing invite-code
  system rather than a new subsystem

### 3.3 Co-parenting across two households
*(divorced, separated, or otherwise non-cohabiting parents sharing
custody)*

Two adults who are not a household unit, who may not want mutual
visibility into each other's calendars or personal logistics, but who
need to share child-specific facts: school events, pickup schedules,
care gaps.

**What this requires:**
- True partitioned visibility, not just "invite more people" — facts
  about the child are shared; facts about each parent's personal
  household are not, by default
- A decision on provenance display: if Exhale learns a fact from Parent
  A's inbox, does Parent B see the fact, the source, both, or neither?
  This needs an explicit answer, not an implicit one
- **This is the architecturally hardest case.** It should inform how the
  data model is shaped now, even if full support is built later —
  retrofitting partitioned visibility after the fact is significantly
  harder than designing the seams in from the start

### 3.4 Multi-generational or non-parent primary caregiver
*(grandparent raising a grandchild, legal guardian, foster family)*

The person running the household may not be "parent" in the data model
at all.

**What this requires:**
- Role and language flexibility in the data model and product surface —
  "primary caregiver" rather than "parent" as the default framing
- Mostly a naming and role-flexibility fix, not a new permission
  architecture — low cost, should not be deferred simply because it's
  minor

## 4. Recommended sequencing

1. **Build for 3.2 next** — cleanest permission-tier problem, broad
   applicability, extends existing infrastructure rather than replacing it
2. **Design the data model with 3.3 in mind now**, even without full
   implementation — the seams (partitioned visibility, provenance
   display rules) are cheap to leave room for today and expensive to
   retrofit later
3. **Handle 3.4 opportunistically** — low cost, can be folded into
   whichever other work touches the caregiver/role model first

## 5. What this addendum does not answer

This is a scoping decision, not a technical spec. Still open:

- The exact permission-tier schema (what granularity of access — per
  child, per day, per obligation type?)
- Whether provenance ("this fact came from Parent A's inbox") is ever
  shown to Parent B, and under what circumstances
- Whether corroboration confidence scoring needs a documented minimum
  floor when only one witness exists, versus flagging low-witness facts
  differently in the UI

These remain genuinely open — recorded here as a register of what's
undecided, not resolved.

---

*This addendum follows the same discipline as §5 of the main project
scope: a conscious, recorded absence rather than a silent one.*
