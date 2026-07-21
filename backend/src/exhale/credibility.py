"""Credibility layer — artifact hierarchy, coverage honesty (§3 hardening).

Born from two real extraction failures during live-Gmail product testing:

* An activity's hours were reported from *typical camp hours* instead of the
  registration email that actually stated them — a plausible default dressed
  up as an observed fact. Fix: every artifact gets an authority tier, facts
  attested only by low-tier artifacts never auto-commit, and unknown values
  stay a named UNKNOWN state (:meth:`exhale.schemas.ExtractionPayload
  .missing_fields`).
* A two-leg family trip was reported as one leg because the second booking
  lived in an inbox the pipeline cannot see. No amount of better searching of
  a connected source fixes a blind spot. Fix: every briefing carries a
  coverage statement naming the connected sources *and* the known-missing
  ones, so an answer that touches an uncovered domain is visibly partial.

The tier vocabulary lives in :mod:`exhale.schemas` (it is part of the data
contract); this module holds the classifier and the coverage builder.
"""

from __future__ import annotations

from exhale.connectors.base import RawMessage
from exhale.schemas import ArtifactTier

# --- Artifact classification ------------------------------------------------------
# Cue vocabularies, matched case-insensitively. Subject cues are the strongest
# signal; body cues are consulted where noted. Precedence: a confirmation beats
# everything (an Airbnb receipt stays a receipt even if it mentions a sale);
# logistics beats marketing; marketing beats reminder/newsletter so a
# "Reminder: sale ends tonight" blast is still marketing.

_CONFIRMATION_CUES = (
    "confirmation", "confirmed", "receipt", "reservation", "itinerary",
    "you're registered", "you are registered", "registration confirmed",
    "your order", "invoice", "booking", "enrolled",
)
_LOGISTICS_CUES = (
    "what you need to know", "know before", "what to bring", "check-in",
    "check in", "drop-off", "drop off", "pick-up", "pickup",
    "getting ready for", "here's what",
)
# Marketing cues are subject-only: promotional subjects are formulaic, while
# body text is where legitimate school mail says things like "bake sale".
_MARKETING_CUES_SUBJECT = (
    "% off", "sale", "savings", "shop now", "free shipping", "clearance",
    "promo code", "coupon", "flash deal", "deals", "new arrivals",
    "limited time", "last chance",
)
_REMINDER_CUES = (
    "reminder", "don't forget", "due soon", "coming up", "upcoming",
    "starts soon", "starts tomorrow",
)
_NEWSLETTER_CUES = (
    "newsletter", "this week at", "weekly update", "digest", "bulletin",
    "what's happening",
)

# Score adjustment the extraction engine applies per tier — small nudges; the
# hard enforcement is the routing ceiling, not the score.
TIER_SCORE_ADJUSTMENT: dict[ArtifactTier, float] = {
    ArtifactTier.CONFIRMATION: 0.06,
    ArtifactTier.LOGISTICS: 0.03,
    ArtifactTier.REMINDER: 0.0,
    ArtifactTier.NEWSLETTER: -0.05,
    ArtifactTier.MARKETING: -0.20,
    ArtifactTier.UNKNOWN: 0.0,
}


def _contains(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def classify_artifact(raw: RawMessage) -> ArtifactTier:
    """Classify a raw message into its authority tier.

    Deterministic and context-free by design: the same artifact always lands
    in the same tier, and the classifier never consults household state.
    """

    subject = (raw.subject or "").lower()
    body_head = (raw.body or "")[:2000].lower()
    both = subject + "\n" + body_head

    if _contains(both, _CONFIRMATION_CUES):
        return ArtifactTier.CONFIRMATION
    if _contains(both, _LOGISTICS_CUES):
        return ArtifactTier.LOGISTICS
    if _contains(subject, _MARKETING_CUES_SUBJECT):
        return ArtifactTier.MARKETING
    if _contains(both, _REMINDER_CUES):
        return ArtifactTier.REMINDER
    if _contains(both, _NEWSLETTER_CUES):
        return ArtifactTier.NEWSLETTER
    return ArtifactTier.UNKNOWN


# --- Coverage honesty ---------------------------------------------------------------
def build_coverage(profile: dict | None) -> dict:
    """Build the coverage statement from a family profile's declaration.

    The profile's ``coverage`` key holds ``connected_sources`` (channel ids the
    pipeline actually reads) and ``known_missing_sources`` (sources the family
    knows exist but has not connected, each with the domains it "owns", e.g.
    a spouse's inbox owning travel bookings, or ParentSquare owning school
    communications). The statement makes the graph's blind spots explicit so
    no answer can silently present itself as complete.
    """

    declared = (profile or {}).get("coverage") or {}
    connected = list(declared.get("connected_sources") or [])
    missing = [dict(m) for m in (declared.get("known_missing_sources") or [])]

    if not connected and not missing:
        statement = (
            "Source coverage undeclared — treat every answer as built from an "
            "unknown fraction of the household's information."
        )
    else:
        parts = [
            f"Built from {len(connected)} connected source(s): "
            f"{', '.join(connected) if connected else 'none'}."
        ]
        if missing:
            gaps = "; ".join(
                f"{m.get('source', 'unknown')} (owns: "
                f"{', '.join(m.get('owns') or []) or 'unspecified'})"
                for m in missing
            )
            parts.append(
                f"Known blind spots: {gaps}. Answers touching those domains "
                "are incomplete by construction."
            )
        statement = " ".join(parts)

    return {
        "connected_sources": connected,
        "known_missing_sources": missing,
        "statement": statement,
    }
