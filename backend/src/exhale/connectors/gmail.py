"""Live Gmail connector (Blueprint §1 connectors, §2 Layer 1).

Pulls real mailbox content through the Gmail REST API v1 and normalizes it into
:class:`~exhale.connectors.base.RawMessage` items for the extraction pipeline.

Auth: either a ready ``access_token``, or an OAuth refresh trio
(``refresh_token`` + ``client_id`` + ``client_secret``) — the connector then
mints/renews access tokens itself and retries once on a 401.

Testability: pass ``http`` (an ``httpx.Client``) to inject a mock transport;
all parsing helpers are pure functions exercised against real Gmail API JSON
shapes in the test suite.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Iterable

import httpx

from exhale.connectors.base import Attachment, Connector, RawMessage

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&#39;": "'", "&quot;": '"'}


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    for entity, char in _ENTITY.items():
        text = text.replace(entity, char)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _header(payload: dict, name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _walk_parts(payload: dict) -> Iterable[dict]:
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _body_text(payload: dict) -> str:
    """Prefer text/plain anywhere in the MIME tree; fall back to stripped HTML."""

    plain, html = [], []
    for part in _walk_parts(payload):
        data = (part.get("body") or {}).get("data")
        if not data or part.get("filename"):
            continue
        mime = part.get("mimeType", "")
        if mime.startswith("text/plain"):
            plain.append(_b64url_decode(data))
        elif mime.startswith("text/html"):
            html.append(_b64url_decode(data))
    if plain:
        return "\n".join(plain)
    if html:
        return "\n".join(_strip_html(h) for h in html)
    return ""


def _attachments(payload: dict) -> tuple[Attachment, ...]:
    out = []
    for part in _walk_parts(payload):
        name = part.get("filename")
        if name:
            out.append(
                Attachment(
                    filename=name,
                    mime_type=part.get("mimeType", "application/octet-stream"),
                    reference=(part.get("body") or {}).get("attachmentId"),
                )
            )
    return tuple(out)


def parse_gmail_message(msg: dict) -> RawMessage:
    """Pure: one Gmail API ``format=full`` message JSON → :class:`RawMessage`."""

    payload = msg.get("payload", {})
    sender = parseaddr(_header(payload, "From"))[1] or None
    domain = sender.split("@", 1)[1].lower() if sender and "@" in sender else None
    internal_ms = int(msg.get("internalDate", 0))
    received = (
        datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc)
        if internal_ms
        else datetime.now(timezone.utc)
    )
    return RawMessage(
        source_id=f"gmail_{msg.get('id', 'unknown')}",
        channel="gmail",
        subject=_header(payload, "Subject").strip(),
        body=_body_text(payload),
        received_at=received,
        sender=sender,
        sender_domain=domain,
        attachments=_attachments(payload),
    )


class GmailConnector(Connector):
    channel = "gmail"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        query: str = "",
        max_messages: int = 200,
        http: httpx.Client | None = None,
    ) -> None:
        if not access_token and not (refresh_token and client_id and client_secret):
            raise ValueError(
                "GmailConnector needs an access_token, or refresh_token + "
                "client_id + client_secret"
            )
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self.query = query
        self.max_messages = max_messages
        self._http = http or httpx.Client(timeout=30)

    # -- auth ------------------------------------------------------------------
    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise PermissionError("Gmail access token rejected and no refresh token available")
        resp = self._http.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]

    def _get(self, url: str, params: dict) -> dict:
        if self._access_token is None:
            self._refresh_access_token()
        for attempt in (1, 2):
            resp = self._http.get(
                url, params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            if resp.status_code == 401 and attempt == 1:
                self._refresh_access_token()
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")

    # -- fetch -----------------------------------------------------------------
    def fetch(self, since: datetime | None = None) -> Iterable[RawMessage]:
        q = self.query
        if since is not None:
            q = f"{q} after:{int(since.timestamp())}".strip()

        fetched = 0
        page_token: str | None = None
        while fetched < self.max_messages:
            params: dict = {"maxResults": min(100, self.max_messages - fetched)}
            if q:
                params["q"] = q
            if page_token:
                params["pageToken"] = page_token
            listing = self._get(f"{GMAIL_API}/users/me/messages", params)

            for ref in listing.get("messages", []) or []:
                msg = self._get(
                    f"{GMAIL_API}/users/me/messages/{ref['id']}", {"format": "full"}
                )
                yield parse_gmail_message(msg)
                fetched += 1
                if fetched >= self.max_messages:
                    return

            page_token = listing.get("nextPageToken")
            if not page_token:
                return
