"""Birthdate-derived signals (ages.py): prompts and grade inference, never decisions."""

from datetime import date, time

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.ages import age_on, age_prompts, grade_for, school_year_start
from exhale.coverage_config import CoverageModelIn

client = TestClient(app)

TODAY = date(2026, 7, 21)


def test_age_on_handles_birthday_boundaries():
    b = date(2014, 7, 22)  # birthday tomorrow relative to TODAY
    assert age_on(b, TODAY) == 11
    assert age_on(b, date(2026, 7, 22)) == 12


def test_school_year_start_rolls_over():
    assert school_year_start(date(2026, 7, 21)) == date(2026, 9, 1)
    assert school_year_start(date(2026, 9, 1)) == date(2026, 9, 1)
    assert school_year_start(date(2026, 9, 2)) == date(2027, 9, 1)


def test_grade_for_kindergarten_cutoff_and_range():
    # Turns 5 on Aug 31 → 5 by Sept 1 → K. A day later → too young → None.
    assert grade_for(date(2021, 8, 31), today=TODAY) == "K"
    assert grade_for(date(2021, 9, 2), today=TODAY) is None
    # A 2020-06-15 kid is 6 by Sept 2026 → grade 1 (the ISLA case shape).
    assert grade_for(date(2020, 6, 15), today=TODAY) == "1"
    # Out of K-12 range → None, not a guess.
    assert grade_for(date(2000, 1, 1), today=TODAY) is None


def _model(children, caregivers=None):
    return CoverageModelIn(**{
        "children": children,
        "caregivers": caregivers or [{"name": "Andy"}],
    })


def test_no_birthdate_means_no_prompts():
    model = _model([{"recipient": {"name": "Stevie"}}])
    assert age_prompts(model, today=TODAY) == []


def test_supervision_review_prompt_fires_only_on_default_window():
    ten_yo = date(2016, 1, 1)
    # Default 6:00–22:00 window → prompt.
    model = _model([{"recipient": {"name": "Kid", "birthdate": ten_yo.isoformat()}}])
    (prompt,) = age_prompts(model, today=TODAY)
    assert prompt["kind"] == "supervised_hours_review"
    assert prompt["age"] == 10
    assert "never loosens this on its own" in prompt["question"]
    assert "USER_CONFIRMED" in prompt["basis"]

    # Family already adjusted the window → Exhale doesn't nag.
    adjusted = _model([{"recipient": {"name": "Kid", "birthdate": ten_yo.isoformat(),
                                      "supervised_start": "06:00:00",
                                      "supervised_end": "17:00:00"}}])
    assert age_prompts(adjusted, today=TODAY) == []


def test_sibling_sitter_prompt_skips_existing_caregivers():
    teen = date(2012, 1, 1)  # 14
    model = _model([{"recipient": {"name": "Jack", "birthdate": teen.isoformat(),
                                   "supervised_start": "07:00:00",
                                   "supervised_end": "21:00:00"}}])
    (prompt,) = age_prompts(model, today=TODAY)
    assert prompt["kind"] == "sibling_sitter"
    assert prompt["child"] == "Jack"

    # Already a caregiver → no suggestion needed.
    already = _model(
        [{"recipient": {"name": "Jack", "birthdate": teen.isoformat(),
                        "supervised_start": "07:00:00",
                        "supervised_end": "21:00:00"}}],
        caregivers=[{"name": "Andy"}, {"name": "Jack", "role": "SITTER"}],
    )
    assert age_prompts(already, today=TODAY) == []


def test_care_watch_carries_age_prompts_through_briefing():
    fam = "fam_age_prompts"
    client.put(f"/v1/families/{fam}/coverage-model", json={
        "children": [
            {"recipient": {"name": "Teen", "birthdate": "2012-01-01"}},
            {"recipient": {"name": "Little", "birthdate": "2022-01-01"}},
        ],
        "caregivers": [{"name": "Andy"}],
    })
    watch = client.get(f"/v1/families/{fam}/briefing").json()["care_watch"]
    kinds = {(p["kind"], p["child"]) for p in watch["age_prompts"]}
    # Teen (≥10, default window) → review prompt; Teen (≥13) → sitter prompt.
    assert ("supervised_hours_review", "Teen") in kinds
    assert ("sibling_sitter", "Teen") in kinds
    # The little one triggers nothing.
    assert not any(p["child"] == "Little" for p in watch["age_prompts"])


def test_birthdate_roundtrips_through_stored_model():
    model = _model([{"recipient": {"name": "Kid", "birthdate": "2020-06-15"}}])
    again = CoverageModelIn(**model.model_dump(mode="json"))
    assert again.children[0].recipient.birthdate == date(2020, 6, 15)
