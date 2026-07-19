"""Deterministic pre-parsing / string cleansing (Blueprint §3.1).

Before the extraction layer looks at a message, strip the noise that wastes
token context and confuses parsing: marketing boilerplate, unsubscribe/footer
blocks, tracking signatures, quoted reply chains, and collapsed whitespace.

Pure string transforms — no I/O — so the cleansing is deterministic and testable.
"""

from __future__ import annotations

import re

# Lines at/after these markers are almost always footer/boilerplate noise.
_FOOTER_MARKERS = (
    "unsubscribe",
    "to stop receiving",
    "manage your preferences",
    "update your preferences",
    "view this email in your browser",
    "this email was sent to",
    "you are receiving this",
    "©",
    "copyright",
    "all rights reserved",
    "sent from my iphone",
    "confidentiality notice",
)

# Quoted-reply chain starts (English + common client formats).
_QUOTE_MARKERS = re.compile(
    r"^\s*(on .+ wrote:|-{2,}\s*original message\s*-{2,}|from:\s.+|>{1,}\s?)",
    re.IGNORECASE,
)

_URL_RE = re.compile(r"https?://\S+")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")


def strip_footer(text: str) -> str:
    """Drop everything from the first footer/boilerplate marker onward."""

    lines = text.splitlines()
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if any(marker in low for marker in _FOOTER_MARKERS):
            return "\n".join(lines[:i]).rstrip()
    return text


def strip_quoted_reply(text: str) -> str:
    """Drop a trailing quoted-reply chain."""

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _QUOTE_MARKERS.match(line):
            return "\n".join(lines[:i]).rstrip()
    return text


def normalize_whitespace(text: str) -> str:
    text = _MULTISPACE_RE.sub(" ", text)
    text = _MULTINEWLINE_RE.sub("\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def clean(text: str, *, drop_urls: bool = False) -> str:
    """Full cleansing pass over a raw message body (§3.1)."""

    text = strip_quoted_reply(text)
    text = strip_footer(text)
    if drop_urls:
        text = _URL_RE.sub("", text)
    return normalize_whitespace(text)
