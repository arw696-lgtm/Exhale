"""Which model does which job, and how hard it should think.

Every LLM path in Exhale shipped on Opus with adaptive thinking and a 16k
ceiling. Opus bills $5/$25 per million tokens and *thinking bills as output*,
so "is this a pizza coupon or a permission slip?" was being answered at
premium rates with premium deliberation. That is a sledgehammer on a
thumbtack, and it showed up on a real family's bill.

Jobs are not equal, so they no longer get equal tools:

* **triage** — junk or not? Pure classification over text that is usually
  obviously one or the other. Haiku, minimal thinking.
* **email** — read prose the regex engine couldn't: reschedules buried in
  paragraphs, implied deadlines. Genuinely needs reading comprehension, but
  not deep reasoning. Sonnet, low effort.
* **vision** — read a photographed school-year calendar or a season
  schedule: dense, skewed, sometimes handwritten, and a misread date becomes
  a missed pickup. The one extraction job worth real capability.
* **concierge** — talks to a person in their own home. Low volume, high
  visibility; quality is the product here.

Every default is overridable per purpose (EXHALE_MODEL_TRIAGE and friends),
with EXHALE_LLM_MODEL / EXHALE_VISION_MODEL still honored for the extraction
paths so existing deployments keep working.
"""

from __future__ import annotations

import os

# Job → (model, effort). Effort is the first cost lever: it trades thinking
# depth within a model, and classification-shaped work does not repay depth.
_DEFAULTS: dict[str, tuple[str, str]] = {
    "triage": ("claude-haiku-4-5", "low"),
    "email": ("claude-sonnet-5", "low"),
    "vision": ("claude-sonnet-5", "medium"),
    "concierge": ("claude-opus-5", "medium"),
}

# Legacy single-knob overrides, honored so existing .env files keep working.
_LEGACY_ENV: dict[str, str] = {
    "email": "EXHALE_LLM_MODEL",
    "triage": "EXHALE_LLM_MODEL",
    "vision": "EXHALE_VISION_MODEL",
}


def model_for(purpose: str) -> str:
    """The model to use for ``purpose``; env overrides beat the default."""

    default, _ = _DEFAULTS.get(purpose, _DEFAULTS["email"])
    specific = os.environ.get(f"EXHALE_MODEL_{purpose.upper()}", "").strip()
    if specific:
        return specific
    legacy = os.environ.get(_LEGACY_ENV.get(purpose, ""), "").strip()
    return legacy or default


def effort_for(purpose: str) -> str:
    """How hard to think for ``purpose`` — 'low' | 'medium' | 'high' | ..."""

    _, default = _DEFAULTS.get(purpose, _DEFAULTS["email"])
    return os.environ.get(f"EXHALE_EFFORT_{purpose.upper()}", "").strip() or default


def output_config(purpose: str) -> dict:
    """The ``output_config`` fragment for a request (effort only)."""

    return {"effort": effort_for(purpose)}
