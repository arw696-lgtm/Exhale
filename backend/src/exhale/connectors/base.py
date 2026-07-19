"""Connector base types (Blueprint §2 Layer 1).

A :class:`RawMessage` is the normalized, channel-agnostic unit every connector
yields — whatever the source (Gmail, Microsoft Graph, IMAP, WebCal, an uploaded
PDF, a voice-note transcript), it arrives here as the same shape so the
extraction layer never needs to know where it came from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class Attachment:
    """A file riding along with a message (permission slip PDF, supply list…)."""

    filename: str
    mime_type: str
    # Extracted/OCR'd text of the attachment, when available (§3.1).
    text: str | None = None
    reference: str | None = None  # opaque handle for later fetch (drive id, cid)


@dataclass(frozen=True)
class RawMessage:
    """A single unstructured item pulled from a household channel."""

    source_id: str                 # opaque provenance handle (gmail msg id, etc.)
    channel: str                   # gmail | msgraph | imap | webcal | upload | voice
    subject: str
    body: str
    received_at: datetime
    sender: str | None = None
    sender_domain: str | None = None
    attachments: tuple[Attachment, ...] = field(default_factory=tuple)

    @property
    def display_name(self) -> str:
        """Human-readable source name for provenance (§9.2)."""

        return self.subject or (self.sender or self.channel)


class Connector(ABC):
    """Abstract pull-based source of :class:`RawMessage` items."""

    #: Short channel identifier stamped onto emitted messages.
    channel: str = "generic"

    @abstractmethod
    def fetch(self, since: datetime | None = None) -> Iterable[RawMessage]:
        """Yield messages received at/after ``since`` (all if ``None``)."""
        raise NotImplementedError
