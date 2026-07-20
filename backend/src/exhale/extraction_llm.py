"""LLM-backed extraction engine (Blueprint §3, roadmap upgrade).

Implements the same interface as the deterministic
:func:`exhale.extraction.extract_payload` — one :class:`RawMessage` in, one
validated :class:`ExtractionPayload` (or ``None``) out — but uses Claude with
structured outputs to read prose the regex heuristics can't: reschedules buried
in paragraphs, implicit obligations, multi-event newsletters, odd phrasings.

Two classes:

* :class:`LLMExtractor` — the raw Claude-backed extractor. Structured outputs
  (``messages.parse`` + a Pydantic contract mirroring §3.2) guarantee the
  response validates; §3.2's fail-cleanly-to-null rule is enforced in the
  prompt and again in post-validation.
* :class:`HybridExtractor` — the production composition: run the deterministic
  engine first, and only when it is *not* HIGH-confidence consult the LLM.
  HIGH-band deterministic extractions never cost an API call, and any LLM
  failure degrades gracefully back to the deterministic result.

Enable via ``EXHALE_LLM_EXTRACTOR=1`` (credentials resolve through the standard
Anthropic SDK chain: ``ANTHROPIC_API_KEY``, auth token, or an ``ant auth login``
profile). Model override: ``EXHALE_LLM_MODEL``.
"""

from __future__ import annotations

import os
from datetime import date

from pydantic import BaseModel, Field

from exhale.connectors.base import RawMessage
from exhale.connectors.preprocess import clean
from exhale.extraction import ExtractionContext, extract_payload
from exhale.routing import ConfidenceBand, classify_confidence
from exhale.schemas import ExtractionPayload

DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = """\
You are the extraction engine for Exhale, a household operating system that \
catches family obligations (school forms, sports registrations, medical \
appointments, camps, payments) before they are forgotten.

You receive ONE message (email or similar) from a household's inbox. Extract \
at most one primary trackable item according to these rules:

1. TRACKABLE means a concrete schedulable event or actionable obligation for \
the household: field trips, permission slips, registrations, practices, \
appointments, deadlines, payments, supply lists, camp sessions. Marketing, \
newsletters with no action, receipts for completed purchases, and pure \
conversation are NOT trackable — set contains_trackable_item to false.
2. NEVER GUESS. Any field you cannot support directly from the message text \
must be null. It is better to return null than a fabricated value.
3. Resolve relative dates ("tomorrow", "next week", "this Friday") against \
the message's SENT date, which is provided. If a date has no year, choose the \
occurrence closest to the sent date that makes sense in context.
4. event_date = the date the primary event takes place. deadline_date = the \
hard action cutoff (due / RSVP / register / sign by), or null if none exists. \
On a reschedule notice, the NEW confirmed date is the event date — never the \
canceled one.
5. target_person_name: only when one of the known family members is clearly \
the subject; otherwise null.
6. action_required: true when a manual step is needed (sign, pay, register, \
submit, reply, bring something).
7. confidence_score calibration (drives automated routing): 0.92-1.0 only \
when the event and its dates are explicit and unambiguous; 0.70-0.91 when \
mostly clear but with one fuzzy element (relative date, implied person); \
below 0.70 when speculative."""


class LLMUnavailable(Exception):
    """The LLM could not produce a usable extraction (API error or refusal)."""


class _LLMExtraction(BaseModel):
    """Structured-output contract the model must produce (mirrors §3.2)."""

    contains_trackable_item: bool = Field(
        description="False when the message holds no schedulable event or actionable obligation."
    )
    extracted_event: str | None = Field(
        description="Human-readable title of the primary event/obligation; null if none."
    )
    target_person_name: str | None = Field(
        description="The known family member this concerns, or null."
    )
    event_date: date | None = Field(
        description="Date the primary event takes place (ISO), or null."
    )
    deadline_date: date | None = Field(
        description="Hard action cutoff date (ISO), or null when there is none."
    )
    action_required: bool = Field(
        description="True when a manual follow-up step is required."
    )
    confidence_score: float = Field(
        description="Parsing certainty in [0,1], calibrated per the system rules."
    )


class LLMExtractor:
    """Claude-backed §3.2 extractor with the standard extractor interface."""

    def __init__(self, *, model: str = DEFAULT_MODEL, client=None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model

    def extract(
        self, raw: RawMessage, ctx: ExtractionContext | None = None
    ) -> ExtractionPayload | None:
        ctx = ctx or ExtractionContext()
        body = clean(raw.body)
        attachment_text = "\n".join(a.text for a in raw.attachments if a.text)

        known = ", ".join(ctx.known_children) or "(none provided)"
        prompt = (
            f"Known family members: {known}\n"
            f"Message sent: {raw.received_at.date().isoformat()}\n"
            f"From: {raw.sender or 'unknown'}\n"
            f"Subject: {raw.subject or '(no subject)'}\n\n"
            f"{body}"
            + (f"\n\n[Attachment text]\n{attachment_text}" if attachment_text else "")
        )

        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_format=_LLMExtraction,
            )
        except Exception as exc:  # SDK errors → let the caller degrade gracefully
            raise LLMUnavailable(str(exc)) from exc

        result = response.parsed_output
        if result is None:  # refusal or schema-parse failure
            raise LLMUnavailable(
                f"no parsed output (stop_reason={getattr(response, 'stop_reason', None)})"
            )

        if (
            not result.contains_trackable_item
            or result.extracted_event is None
            or result.event_date is None
        ):
            return None

        return ExtractionPayload(
            extracted_event=result.extracted_event,
            target_person_name=result.target_person_name,
            event_date=result.event_date,
            deadline_date=result.deadline_date,
            action_required=result.action_required,
            confidence_score=round(min(max(result.confidence_score, 0.0), 1.0), 4),
            # Provenance comes from the pipeline, never from the model.
            source_document_name=raw.display_name,
            source_reference=raw.source_id,
        )


class HybridExtractor:
    """Deterministic first; LLM only for what the heuristics can't nail.

    * Deterministic result in the HIGH band → returned as-is, zero API cost.
    * Otherwise the LLM is consulted and its judgment wins (including "not
      trackable" → ``None``).
    * If the LLM is unavailable, the deterministic result (possibly ``None``)
      stands — the pipeline never breaks because the API is down.
    """

    def __init__(self, llm: LLMExtractor) -> None:
        self.llm = llm

    def extract(
        self, raw: RawMessage, ctx: ExtractionContext | None = None
    ) -> ExtractionPayload | None:
        deterministic = extract_payload(raw, ctx)
        if (
            deterministic is not None
            and classify_confidence(deterministic.confidence_score)
            is ConfidenceBand.HIGH
        ):
            return deterministic

        try:
            return self.llm.extract(raw, ctx)
        except LLMUnavailable:
            return deterministic


def extractor_from_env():
    """The extractor callable the pipeline should use, per environment config.

    ``EXHALE_LLM_EXTRACTOR=1`` enables the hybrid LLM path (requires Anthropic
    credentials); anything else keeps the pure deterministic engine.
    """

    if os.environ.get("EXHALE_LLM_EXTRACTOR", "").strip().lower() in ("1", "true", "yes"):
        model = os.environ.get("EXHALE_LLM_MODEL", DEFAULT_MODEL)
        return HybridExtractor(LLMExtractor(model=model)).extract
    return extract_payload
