"""The app has to fit a phone. Enforced by grep, for the same reason as
``test_ui_contrast``: a layout rule nobody checks lasts one refactor.

Exhale is opened on a phone, for three seconds, one-handed. It was instead
being pinched smaller and dragged left and right to read. Two independent
causes, both fixed here and both guarded:

* **iOS zooms the page when a focused control renders under 16px** — and it
  never zooms back out. Every text field in the app was 13–15px, so the first
  tap on the login screen left it zoomed and adrift. The 16px floor lives in
  index.css, but a Tailwind utility beats a base-layer element selector, so
  the controls must not carry ``text-xs``/``text-sm``.

* **Long real-world strings widened the page.** A school-district sender
  address or a published .ics link is longer than any phone is wide; measured
  against realistic data the page opened to 471px of content on a 320px
  screen. Only ``overflow-wrap: anywhere`` fixes it — ``break-word`` leaves
  the element's *min-content* width untouched, and that intrinsic size is
  what forces the page open.

And the fix that must never be applied: disabling pinch-zoom. It silences the
symptom for the person least able to afford it.
"""

import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"
COMPONENTS = sorted((FRONTEND / "src").rglob("*.jsx"))
INDEX_CSS = FRONTEND / "src" / "index.css"
INDEX_HTML = FRONTEND / "index.html"

_TAG = re.compile(r"<(input|textarea|select)\b")
# Focusing these opens no keyboard, so they never trigger the zoom.
_NO_KEYBOARD = {"checkbox", "radio", "file", "range", "color", "submit", "button", "hidden"}


def _element_span(src, i):
    """The exact source of the JSX element starting at src[i] == '<'.

    Attribute values hold arrow functions, so a naive scan to the first '>'
    stops inside ``onChange={(e) => ...}``. Track braces and quotes instead.
    """
    depth, quote, j = 0, None, i + 1
    while j < len(src):
        c = src[j]
        if quote:
            if c == quote and src[j - 1] != "\\":
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return src[i : j + 1]
        j += 1
    raise AssertionError(f"unterminated JSX element at offset {i}")


def _text_entry_controls():
    """(location, classes) for every control that opens a keyboard."""
    for path in COMPONENTS:
        src = path.read_text()
        for m in _TAG.finditer(src):
            el = _element_span(src, m.start())
            kind = re.search(r'type="([^"]+)"', el)
            if kind and kind.group(1) in _NO_KEYBOARD:
                continue
            classes = re.search(r'className="([^"]*)"', el)
            line = src[: m.start()].count("\n") + 1
            yield f"{path.name}:{line}", (classes.group(1) if classes else "")


def test_controls_were_found():
    """Guard the guard: a broken scan would make the rule below vacuous."""

    found = list(_text_entry_controls())
    assert len(found) > 15, found


def test_no_text_entry_control_is_under_16px():
    offenders = [
        f"{where}  {classes[:88]}"
        for where, classes in _text_entry_controls()
        if re.search(r"\btext-(?:xs|sm)\b(?!-)", classes)
    ]
    assert not offenders, (
        "These controls render under 16px, so iOS zooms the page on focus and "
        "never zooms back. Drop the size class and take the 16px base floor:\n  "
        + "\n  ".join(offenders)
    )


def test_the_sixteen_pixel_floor_is_declared():
    css = INDEX_CSS.read_text()
    block = re.search(
        r"input,\s*textarea,\s*select\s*\{[^}]*font-size:\s*16px", css, re.S
    )
    assert block, "index.css must set the 16px floor on input/textarea/select"


def test_long_strings_wrap_instead_of_widening_the_page():
    css = INDEX_CSS.read_text()
    assert re.search(r"overflow-wrap:\s*anywhere", css), (
        "body needs `overflow-wrap: anywhere`. `break-word` is not a "
        "substitute — it leaves min-content width alone, which is what "
        "actually forces the page wider than the screen."
    )


@pytest.mark.parametrize("banned", ["maximum-scale", "user-scalable"])
def test_pinch_zoom_is_never_disabled(banned):
    """The tempting wrong fix for all of the above.

    Locking the viewport hides overflow and stops the iOS focus-zoom, at the
    cost of the reader who most needs to magnify the screen. Fix the sizes.
    """

    viewport = re.search(
        r'<meta[^>]*name="viewport"[^>]*>', INDEX_HTML.read_text(), re.S
    )
    assert viewport, "index.html has no viewport meta"
    assert banned not in viewport.group(0), (
        f"{banned} disables pinch-zoom. Exhale is built for someone who "
        "magnifies the screen; fix the control sizes instead."
    )
