"""Reference IMAP/email connector (Blueprint §2 Layer 1, §1 connectors).

A thin, standard-library adapter that turns an IMAP mailbox into
:class:`~exhale.connectors.base.RawMessage` items. It is intentionally minimal —
credentials in, normalized messages out — and documents the shape any richer
connector (Gmail API, Microsoft Graph) should implement.

Not exercised in unit tests (it needs a live server); the parsing helper
:func:`message_from_bytes` is pure and testable.
"""

from __future__ import annotations

import email
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Iterable

from exhale.connectors.base import Attachment, Connector, RawMessage


def _body_text(msg: Message) -> str:
    """Best-effort plain-text body extraction from an email message."""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""


def _attachments(msg: Message) -> tuple[Attachment, ...]:
    out: list[Attachment] = []
    if msg.is_multipart():
        for part in msg.walk():
            name = part.get_filename()
            if name:
                out.append(Attachment(filename=name, mime_type=part.get_content_type()))
    return tuple(out)


def message_from_bytes(raw_bytes: bytes, *, source_id: str, channel: str = "imap") -> RawMessage:
    """Parse raw RFC-822 bytes into a normalized :class:`RawMessage` (pure)."""

    msg = email.message_from_bytes(raw_bytes)
    sender = email.utils.parseaddr(msg.get("From", ""))[1] or None
    domain = sender.split("@", 1)[1].lower() if sender and "@" in sender else None
    try:
        received = parsedate_to_datetime(msg.get("Date"))
    except (TypeError, ValueError):
        received = datetime.now(timezone.utc)
    if received and received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)

    return RawMessage(
        source_id=source_id,
        channel=channel,
        subject=str(msg.get("Subject", "")).strip(),
        body=_body_text(msg),
        received_at=received or datetime.now(timezone.utc),
        sender=sender,
        sender_domain=domain,
        attachments=_attachments(msg),
    )


class ImapConnector(Connector):
    channel = "imap"

    def __init__(self, host: str, username: str, password: str, mailbox: str = "INBOX", *, ssl: bool = True) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.mailbox = mailbox
        self.ssl = ssl

    def fetch(self, since: datetime | None = None) -> Iterable[RawMessage]:  # pragma: no cover - needs live server
        import imaplib

        client = (imaplib.IMAP4_SSL if self.ssl else imaplib.IMAP4)(self.host)
        try:
            client.login(self.username, self.password)
            client.select(self.mailbox)
            criteria = ["ALL"]
            if since is not None:
                criteria = ["SINCE", since.strftime("%d-%b-%Y")]
            _typ, data = client.search(None, *criteria)
            for num in data[0].split():
                _typ, msg_data = client.fetch(num, "(RFC822)")
                if msg_data and msg_data[0]:
                    yield message_from_bytes(
                        msg_data[0][1], source_id=f"imap_{num.decode()}", channel=self.channel
                    )
        finally:
            try:
                client.logout()
            except Exception:  # noqa: BLE001
                pass
