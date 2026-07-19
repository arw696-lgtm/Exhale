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

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


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
