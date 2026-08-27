"""Tests for the model/effort policy.

These pin a cost decision, not an implementation detail: every LLM path once
ran on Opus with adaptive thinking, and "is this a pizza coupon or a
permission slip?" was being answered at premium rates with premium
deliberation. A regression here is a bill, not a bug report.
"""

from exhale.costs import estimate_cost_usd
from exhale.model_policy import effort_for, model_for, output_config


def test_classification_work_does_not_run_on_the_priciest_model():
    """Triage is junk-or-real. It must not cost Opus rates."""

    triage = model_for("triage")
    assert "opus" not in triage
    assert "fable" not in triage
    # And it must not deliberate deeply over marketing email.
    assert effort_for("triage") == "low"


def test_email_reading_is_mid_tier_and_shallow():
    assert model_for("email") == "claude-sonnet-5"
    assert effort_for("email") == "low"


def test_vision_keeps_real_capability():
    """A misread date on a school calendar becomes a missed pickup — this is
    the one extraction job worth paying for."""

    assert effort_for("vision") in ("medium", "high")


def test_concierge_keeps_quality_where_a_person_reads_it():
    assert "opus" in model_for("concierge")


def test_triage_is_dramatically_cheaper_than_the_old_default():
    """The concrete win: same 38-email sweep, a fraction of the money."""

    old = estimate_cost_usd("claude-opus-4-8", 1500, 700)
    new = estimate_cost_usd(model_for("triage"), 1500, 700)
    assert new < old / 4


def test_env_overrides_win_per_purpose(monkeypatch):
    monkeypatch.setenv("EXHALE_MODEL_TRIAGE", "claude-opus-5")
    monkeypatch.setenv("EXHALE_EFFORT_TRIAGE", "high")
    assert model_for("triage") == "claude-opus-5"
    assert output_config("triage") == {"effort": "high"}


def test_legacy_single_knob_still_honored(monkeypatch):
    """Existing .env files that set EXHALE_LLM_MODEL keep working."""

    monkeypatch.setenv("EXHALE_LLM_MODEL", "claude-haiku-4-5")
    assert model_for("email") == "claude-haiku-4-5"


def test_sonnet_5_prices_below_sonnet_4_6():
    """Prefix matching must not price Sonnet 5 at its predecessor's rate."""

    assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 0) == 2.00
    assert estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 0) == 3.00
