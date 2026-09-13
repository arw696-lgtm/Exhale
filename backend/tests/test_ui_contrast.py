"""A contrast floor for the interface, enforced by grep.

This lives in the Python suite because it is the only test runner the repo
has, and an unenforced accessibility rule is a rule that lasts one refactor.

The app was shipped with body copy at 3.97:1, labels at 2.63:1, and — worst —
its two *information-bearing* accents below even the 3:1 large-text floor:
sage at 2.95:1 on every link, amber at 2.39:1 on every deadline. The person
it was built for couldn't read it. "Calm" is not a licence for low contrast.

Two rules, both measured in exhale's own palette (see frontend/src/index.css):

* ink text never drops below /70 — 5.37:1 on light, 6.94:1 on dark
* sage-release / looming-amber are DECORATIVE (fills, halos, dots). Anything
  a person reads uses sage-text / amber-text, which clear 4.5:1 on both
  surfaces.
"""

import pathlib
import re

import pytest

COMPONENTS = sorted(
    (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src").rglob("*.jsx")
)

# Opacities below the floor, as they appear on the ink token.
_TOO_FAINT = re.compile(r"text-sanctuary-navy/(?:[0-5]?\d|6[0-9])\b")
# A decorative accent used as a text colour.
_DECORATIVE_AS_TEXT = re.compile(r"\btext-(?:sage-release|looming-amber)\b")
# White knocked out of a decorative fill — 2.1:1 on amber, 2.3:1 on sage.
# Only -text accents and solid ink are dark enough to carry white.
_WHITE_ON_DECORATIVE = re.compile(
    r"bg-(?:sage-release|looming-amber)\b(?![-/])[^\"']*\btext-white\b"
    r"|\btext-white\b[^\"']*\bbg-(?:sage-release|looming-amber)\b(?![-/])"
)
# A hover that lands on the colour it started from: the affordance is gone and
# the rest state never lifts. Raising a faint colour to the floor can create
# these by collision, so the guard watches for it.
# The capture must span the WHOLE colour, opacity suffix included — matching
# only up to a word break makes `navy/70` look identical to `navy`.
_DEAD_HOVER = re.compile(
    r"\btext-([a-z0-9-]+(?:/\d{1,3})?)(?![\w/-])[^\"']*"
    r"\bhover:text-\1(?![\w/-])"
)


def _offenders(pattern):
    hits = []
    for path in COMPONENTS:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.name}:{n}  {line.strip()[:88]}")
    return hits


def test_components_exist():
    """Guard the guard: a bad path would make every rule below vacuous."""

    assert len(COMPONENTS) > 10, COMPONENTS


def test_no_text_below_the_contrast_floor():
    offenders = _offenders(_TOO_FAINT)
    assert not offenders, (
        "Ink text below /70 (under 5.37:1 on light). Raise it:\n  "
        + "\n  ".join(offenders)
    )


def test_decorative_accents_are_never_used_as_text():
    offenders = _offenders(_DECORATIVE_AS_TEXT)
    assert not offenders, (
        "sage-release/looming-amber are fill colours (2.95:1 and 2.39:1 as "
        "text on light). Use text-sage-text / text-amber-text:\n  "
        + "\n  ".join(offenders)
    )


def test_white_is_never_knocked_out_of_a_decorative_fill():
    offenders = _offenders(_WHITE_ON_DECORATIVE)
    assert not offenders, (
        "White on sage-release/looming-amber is 2.1–2.3:1. Use bg-sage-text / "
        "bg-amber-text, or ink text on the pale fill:\n  " + "\n  ".join(offenders)
    )


def test_hover_states_actually_change_the_colour():
    offenders = _offenders(_DEAD_HOVER)
    assert not offenders, (
        "Hover resolves to the rest colour — no affordance, and the rest "
        "state never lifts:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("token", ["--sage-text", "--amber-text"])
def test_text_accent_tokens_are_defined_for_both_themes(token):
    css = (pathlib.Path(__file__).resolve().parents[2]
           / "frontend" / "src" / "index.css").read_text()
    # Root, the dark media query, and both explicit data-theme blocks.
    assert css.count(token) >= 4, f"{token} missing from a theme block"
