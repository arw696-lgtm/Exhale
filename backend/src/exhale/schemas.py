"""Layer 2 — Extraction data contract (blueprint §3.2).

Every noisy, unstructured input (email body, OCR'd PDF, screenshot, voice-note
transcript) that flows through the ingestion pipeline must be normalized into a
single validated contract: :class:`ExtractionPayload`.

Design rules mirrored from the PRD:

* Optional entities that cannot be derived with baseline semantic proof fail
  *cleanly* over to ``None`` rather than being guessed.
* ``confidence_score`` is a hard-bounded probability index in ``[0.0, 1.0]``.
* ``required`` fields (event, date, action flag, confidence) must always be
  present for a payload to be considered valid.
"""

from __future__ import annotations

from datetime import date, time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ArtifactTier(str, Enum):
    """How authoritative the source artifact is (credibility layer).

    Confirmations *establish* facts. Logistics notices carry operational detail
    straight from the organizer. Reminders and newsletters merely *reference*
    facts established elsewhere. Marketing establishes nothing. Routing (§3.3)
    treats the tier as a hard ceiling: a fact attested only by a low-tier
    artifact can never silently auto-commit to the graph.
    """

    CONFIRMATION = "CONFIRMATION"
    LOGISTICS = "LOGISTICS"
    REMINDER = "REMINDER"
    NEWSLETTER = "NEWSLETTER"
    MARKETING = "MARKETING"
    UNKNOWN = "UNKNOWN"


class FactOrigin(str, Enum):
    """Whether a value was read from an artifact or filled in by the pipeline.

    OBSERVED means the value appears in the source artifact and can be cited.
    INFERRED means the pipeline derived it (a relative phrase, a pattern, a
    default) — inferred values must never be presented as observed, and never
    auto-commit. USER_CONFIRMED is ground truth from a human correction and
    outranks everything.
    """

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    USER_CONFIRMED = "USER_CONFIRMED"


class ExtractionPayload(BaseModel):
    """A single structured extraction produced from one unstructured input.

    This is the programmatic equivalent of the JSON Schema in blueprint §3.2.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    extracted_event: str = Field(
        ...,
        min_length=1,
        description="The human-readable core intent or title of the extracted event.",
    )
    target_person_name: str | None = Field(
        default=None,
        description="Specific child or family member the action or event applies to.",
    )
    event_date: date = Field(
        ...,
        description="The exact calendar date the primary event takes place.",
    )
    deadline_date: date | None = Field(
        default=None,
        description="The hard action cutoff date for signatures, paperwork, or payments.",
    )
    action_required: bool = Field(
        ...,
        description="Flag indicating if manual follow-up or administrative action is required.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The pipeline probability index indicating parsing certainty.",
    )
    # Provenance is not part of the minimal §3.2 contract but is required for the
    # Provenance Popover (§9.2). It is optional so pure extraction stays testable.
    source_document_name: str | None = Field(
        default=None,
        description="Human-readable name of the source artifact (email subject, file name).",
    )
    source_reference: str | None = Field(
        default=None,
        description="Opaque provenance handle (message id, drive file id) for source lookup.",
    )
    # --- Credibility layer -------------------------------------------------------
    artifact_tier: ArtifactTier = Field(
        default=ArtifactTier.UNKNOWN,
        description="Authority class of the source artifact; a routing ceiling.",
    )
    event_date_origin: FactOrigin = Field(
        default=FactOrigin.OBSERVED,
        description="Whether the event date was read from the artifact or inferred.",
    )
    event_start_time: time | None = Field(
        default=None,
        description="Observed start time of the event window; null means UNKNOWN, never a guess.",
    )
    event_end_time: time | None = Field(
        default=None,
        description="Observed end time of the event window; null means UNKNOWN, never a guess.",
    )
    corrects: str | None = Field(
        default=None,
        description="extraction_id of the ledger entry this user correction supersedes.",
    )

    def missing_fields(self) -> list[str]:
        """Expected-but-unknown fields — a named state, never a filled default.

        Downstream surfaces (ledger, obligation nodes, UI) render these as
        explicit gaps ("hours unknown — check the registration") instead of
        letting a plausible-sounding placeholder stand in for knowledge.
        """

        missing: list[str] = []
        if self.event_start_time is None:
            missing.append("event_time_window")
        if self.target_person_name is None:
            missing.append("target_person_name")
        if self.action_required and self.deadline_date is None:
            missing.append("deadline_date")
        return missing
