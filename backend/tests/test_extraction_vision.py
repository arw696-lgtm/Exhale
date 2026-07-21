"""Tests for the vision extractor (§1–3, photos & screenshots)."""

from datetime import date, time

import pytest

from exhale.extraction import ExtractionContext
from exhale.extraction_vision import (
    VisionExtractor,
    VisionUnavailable,
    _VisionExtraction,
    _VisionItem,
    vision_extractor_from_env,
)
from exhale.schemas import ArtifactTier, FactOrigin


# --- stub Anthropic client --------------------------------------------------------
class _StubResponse:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _StubMessages:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _StubClient:
    def __init__(self, outcome):
        self.messages = _StubMessages(outcome)


def _item(**over):
    base = dict(
        extracted_event="Junior Robotics Camp",
        target_person_name="Stevie",
        event_date=date(2026, 7, 20),
        event_date_stated_explicitly=True,
        event_start_time=time(13, 0),
        event_end_time=time(16, 0),
        deadline_date=None,
        action_required=True,
        artifact_tier=ArtifactTier.LOGISTICS,
        confidence_score=0.9,
    )
    base.update(over)
    return _VisionItem(**base)


def _doc(*items, kind="camp flyer"):
    return _StubResponse(_VisionExtraction(document_kind=kind, items=list(items)))


CTX = ExtractionContext(known_children=["Stevie"])
PNG = ("iVBORw0KGgo=", "image/png")


def _extract(outcome, **over):
    kw = dict(source_name="IMG_2662.png", source_reference="photo_abc", ctx=CTX)
    kw.update(over)
    return VisionExtractor(client=_StubClient(outcome)).extract(*PNG, **kw)


# --- mapping ----------------------------------------------------------------------
def test_single_item_maps_with_observed_times_and_provenance():
    payloads = _extract(_doc(_item()))
    assert len(payloads) == 1
    p = payloads[0]
    assert p.extracted_event == "Junior Robotics Camp"
    assert p.event_date == date(2026, 7, 20)
    assert p.event_start_time == time(13, 0)
    assert p.event_end_time == time(16, 0)
    assert p.artifact_tier is ArtifactTier.LOGISTICS
    assert p.event_date_origin is FactOrigin.OBSERVED
    # Provenance stamped by the pipeline, not the model.
    assert p.source_document_name == "IMG_2662.png"
    assert p.source_reference == "photo_abc"


def test_multiple_items_all_extracted():
    payloads = _extract(_doc(
        _item(extracted_event="Game 1", event_date=date(2026, 9, 12)),
        _item(extracted_event="Game 2", event_date=date(2026, 9, 19)),
        kind="soccer schedule"))
    assert [p.extracted_event for p in payloads] == ["Game 1", "Game 2"]


def test_inferred_date_flagged_as_inferred():
    payloads = _extract(_doc(_item(event_date_stated_explicitly=False)))
    assert payloads[0].event_date_origin is FactOrigin.INFERRED


def test_item_without_event_date_is_dropped_not_guessed():
    payloads = _extract(_doc(_item(event_date=None), _item(extracted_event="Real")))
    assert [p.extracted_event for p in payloads] == ["Real"]


def test_empty_items_returns_empty_list():
    assert _extract(_doc(kind="advertisement")) == []


def test_confidence_is_clamped():
    assert _extract(_doc(_item(confidence_score=1.9)))[0].confidence_score == 1.0


def test_missing_time_stays_unknown():
    p = _extract(_doc(_item(event_start_time=None, event_end_time=None)))[0]
    assert p.event_start_time is None
    assert "event_time_window" in p.missing_fields()


# --- request shape & failure ------------------------------------------------------
def test_request_includes_image_block_and_children_context():
    client = _StubClient(_doc(_item()))
    VisionExtractor(client=client).extract(
        *PNG, source_name="f.png", source_reference="photo_1", ctx=CTX)
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["output_format"] is _VisionExtraction
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert "Stevie" in content[1]["text"]


def test_unsupported_media_type_raises():
    with pytest.raises(VisionUnavailable, match="media type"):
        VisionExtractor(client=_StubClient(_doc(_item()))).extract(
            "data", "application/pdf", source_name="x", source_reference="y", ctx=CTX)


def test_api_error_raises_vision_unavailable():
    with pytest.raises(VisionUnavailable):
        _extract(RuntimeError("connection reset"))


def test_refusal_raises_vision_unavailable():
    with pytest.raises(VisionUnavailable, match="refusal"):
        _extract(_StubResponse(None, stop_reason="refusal"))


# --- env factory ------------------------------------------------------------------
def test_env_factory_none_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert vision_extractor_from_env() is None


def test_env_factory_builds_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    extractor = vision_extractor_from_env()
    assert isinstance(extractor, VisionExtractor)
