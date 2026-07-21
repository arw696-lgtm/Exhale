"""Vision extraction engine (Blueprint §1–3 — photos & screenshots).

The "just screenshot it and add it in" path. A photo of a flyer, a school
calendar, a camp confirmation, or a ParentSquare post is a first-class household
artifact — often the *only* place a fact lives (paper flyers, app screenshots
that never hit an inbox). This extractor sends the image to Claude with vision +
structured output and produces the same validated
:class:`~exhale.schemas.ExtractionPayload` objects the text pipeline emits, so
photos flow through the identical routing (§3.3) and credibility rules.

Two differences from the text extractor, both deliberate:

* **Multiple items.** A flyer is usually one event, but a sports schedule or a
  camp with several sessions carries many — so vision returns a *list*.
* **Provenance is stamped by the pipeline, tier and observed/inferred by the
  model's own account.** A time read off the image is OBSERVED; a date the model
  had to infer (a flyer that says "next Friday") is INFERRED and, per the
  routing rules, never auto-commits.

Enable with credentials on the standard Anthropic SDK chain; the image never
touches the deterministic path (there's nothing to parse without vision).
"""

from __future__ import annotations

import os
from datetime import date, time

from pydantic import BaseModel, Field

from exhale.extraction import ExtractionContext
from exhale.schemas import ArtifactTier, ExtractionPayload, FactOrigin

DEFAULT_VISION_MODEL = "claude-opus-4-8"

_ALLOWED_MEDIA = {"image/png", "image/jpeg", "image/webp", "image/gif"}

_VISION_SYSTEM_PROMPT = """\
You are the vision extraction engine for Exhale, a household operating system \
that catches family obligations (school forms, camps, sports, appointments, \
payments) before they are forgotten.

You are given ONE image — a photo or screenshot of a flyer, school calendar, \
camp confirmation, app post, or similar. Extract EVERY distinct trackable item \
you can read, as a list. Rules:

1. TRACKABLE = a concrete schedulable event or actionable obligation for the \
household. A pure marketing/promotional image with no date or action has no \
items — return an empty list.
2. NEVER GUESS. Any field you cannot read directly from the image must be null. \
It is far better to return null than a fabricated value. In particular, only \
give a start/end time if the image actually shows one.
3. For each item set event_date_stated_explicitly = true only when a concrete \
calendar date is visible in the image; false when you inferred it from a \
relative phrase ("next Friday") or surrounding context.
4. Classify each item's artifact_tier from what the image is: a receipt/booking/ \
registration confirmation = CONFIRMATION; a logistics/"what to bring" notice or \
an official calendar = LOGISTICS; a save-the-date reminder = REMINDER; a \
newsletter = NEWSLETTER; an ad = MARKETING.
5. target_person_name only when a known family member is clearly the subject.
6. confidence_score in [0,1]: high only when the event and its dates are clearly \
legible and unambiguous."""


class VisionUnavailable(Exception):
    """The vision model could not produce a usable extraction (error/refusal)."""


class _VisionItem(BaseModel):
    """One trackable item read from the image (mirrors §3.2 + credibility)."""

    extracted_event: str | None = Field(description="Title of the event/obligation; null if unreadable.")
    target_person_name: str | None = Field(description="Known family member this concerns, or null.")
    event_date: date | None = Field(description="Date the event takes place (ISO), or null.")
    event_date_stated_explicitly: bool = Field(
        default=True,
        description="True only if a concrete date is visible; false if inferred.",
    )
    event_start_time: time | None = Field(description="Start time ONLY if shown; else null.")
    event_end_time: time | None = Field(description="End time ONLY if shown; else null.")
    deadline_date: date | None = Field(description="Hard action cutoff (ISO), or null.")
    action_required: bool = Field(description="True if a manual step is needed.")
    artifact_tier: ArtifactTier = Field(description="Authority class of the source image.")
    confidence_score: float = Field(description="Legibility/certainty in [0,1].")


class _VisionExtraction(BaseModel):
    """Structured-output contract: what the model returns for one image."""

    document_kind: str = Field(description="What the image is, e.g. 'camp flyer', 'school calendar'.")
    items: list[_VisionItem] = Field(description="Every distinct trackable item; empty if none.")


_SCHOOL_SYSTEM_PROMPT = """\
You read a school-year calendar image and extract the days a specific student \
has NO SCHOOL, so a household can plan childcare around them.

Rules:
1. Return only weekday closures during the school year (a supervised child needs \
care on a no-school weekday; weekends are already non-school and are not needed).
2. GRADE MATTERS. If the student's grade is given, include only closures that \
apply to that grade. Exclude closures marked for other grades only (e.g. a \
"PK-K only" day is NOT a day off for a 1st grader).
3. NEVER GUESS. If you cannot read the first/last day of school, return null for \
it rather than inventing a date. Give each closure the exact date shown and a \
short reason from the legend/notes ("MEA break", "Winter Break").
4. first_day/last_day are for THIS student (some calendars list different start \
dates per grade band)."""


class _SchoolClosure(BaseModel):
    day: date = Field(description="A weekday the student has no school (ISO).")
    reason: str = Field(description="Short reason from the calendar legend/notes.")


class _SchoolCalendarExtraction(BaseModel):
    """Structured output for a school-calendar image."""

    school_name: str | None = Field(description="School name if visible, else null.")
    first_day: date | None = Field(description="First day of school for this student (ISO), or null.")
    last_day: date | None = Field(description="Last day of school for this student (ISO), or null.")
    no_school_days: list[_SchoolClosure] = Field(
        description="Every weekday-during-term closure that applies to this student."
    )


class VisionExtractor:
    """Claude-vision-backed extractor producing §3.2 payloads from an image."""

    def __init__(self, *, model: str = DEFAULT_VISION_MODEL, client=None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model

    def extract(
        self,
        image_base64: str,
        media_type: str,
        *,
        source_name: str,
        source_reference: str,
        ctx: ExtractionContext | None = None,
    ) -> list[ExtractionPayload]:
        ctx = ctx or ExtractionContext()
        if media_type not in _ALLOWED_MEDIA:
            raise VisionUnavailable(f"unsupported media type: {media_type!r}")

        known = ", ".join(ctx.known_children) or "(none provided)"
        prompt = (
            f"Known family members: {known}\n"
            "Extract every trackable household item you can read in this image."
        )
        content = [
            {"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": image_base64}},
            {"type": "text", "text": prompt},
        ]

        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=_VISION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=_VisionExtraction,
            )
        except Exception as exc:  # SDK / transport errors
            raise VisionUnavailable(str(exc)) from exc

        result = response.parsed_output
        if result is None:
            raise VisionUnavailable(
                f"no parsed output (stop_reason={getattr(response, 'stop_reason', None)})"
            )

        payloads: list[ExtractionPayload] = []
        for item in result.items:
            # Same fail-cleanly rule as the text path: no event date → not trackable.
            if item.extracted_event is None or item.event_date is None:
                continue
            payloads.append(
                ExtractionPayload(
                    extracted_event=item.extracted_event,
                    target_person_name=item.target_person_name,
                    event_date=item.event_date,
                    deadline_date=item.deadline_date,
                    action_required=item.action_required,
                    confidence_score=round(min(max(item.confidence_score, 0.0), 1.0), 4),
                    # Provenance is stamped by the pipeline, never trusted from the model.
                    source_document_name=source_name,
                    source_reference=source_reference,
                    artifact_tier=item.artifact_tier,
                    event_date_origin=FactOrigin.OBSERVED
                    if item.event_date_stated_explicitly
                    else FactOrigin.INFERRED,
                    event_start_time=item.event_start_time,
                    event_end_time=item.event_end_time,
                )
            )
        return payloads


    def extract_school_calendar(
        self,
        image_base64: str,
        media_type: str,
        *,
        grade: str | None = None,
        ctx: ExtractionContext | None = None,
    ) -> _SchoolCalendarExtraction:
        """Read a school-calendar image → the student's no-school days.

        Feeds the Care-Coverage Engine's ``SchoolCalendar`` (the no-school days
        that flip a child from school-covered to needing care), rather than the
        obligation graph. Grade-aware: pass ``grade`` so grade-specific closures
        that don't apply to this student are excluded.
        """

        if media_type not in _ALLOWED_MEDIA:
            raise VisionUnavailable(f"unsupported media type: {media_type!r}")

        who = f"The student is in grade {grade}." if grade else "The student's grade is unspecified."
        content = [
            {"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": image_base64}},
            {"type": "text", "text": f"{who} Extract this student's no-school days."},
        ]
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=_SCHOOL_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=_SchoolCalendarExtraction,
            )
        except Exception as exc:
            raise VisionUnavailable(str(exc)) from exc

        result = response.parsed_output
        if result is None:
            raise VisionUnavailable(
                f"no parsed output (stop_reason={getattr(response, 'stop_reason', None)})"
            )
        return result


def vision_extractor_from_env() -> VisionExtractor | None:
    """A :class:`VisionExtractor` when Anthropic credentials are configured, else None."""

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    model = os.environ.get("EXHALE_VISION_MODEL", DEFAULT_VISION_MODEL)
    return VisionExtractor(model=model)
