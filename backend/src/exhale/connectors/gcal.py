"""Live Google Calendar connector (Blueprint §1 connectors → Care-Coverage).

Pulls a caregiver's real calendar through the Google Calendar REST API v3 and
normalizes each *busy* block into a :class:`~exhale.coverage.CalendarEvent` the
Care-Coverage Engine consumes — turning "when is this parent actually free" from
an inferred assumption into an observed fact.

What counts as a care-blocking event (the honest-defaults discipline):

* only **timed** events block — an all-day marker ("Shot Day") is ambiguous and
  is *not* treated as a full-day blackout;
* only events the owner is marked **busy** for — an event with
  ``transparency: "transparent"`` (Free) does not block care;
* cancelled events are skipped.

Everything mapped is stamped ``origin=OBSERVED`` (it was read off a calendar),
so a coverage gap built from it is high-confidence, not assumption-dependent.

Auth mirrors the Gmail connector: a ready ``access_token`` or an OAuth refresh
trio; ``http`` is injectable for testing. All mapping is a pure function
exercised against real Calendar API JSON shapes in the test suite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx

from exhale.coverage import CalendarEvent
from exhale.schemas import FactOrigin

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _parse_dt(node: dict) -> datetime | None:
    """A Google event start/end node → naive local wall-clock datetime.

    Timed events carry ``dateTime`` (RFC3339, with the local offset); the
    coverage engine works in naive local wall-clock, so we drop the offset —
    the wall-clock reading is exactly the datetime portion. All-day events carry
    only ``date`` and return ``None`` (they are not treated as timed blocks).
    """

    value = node.get("dateTime")
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=None)


def parse_calendar_event(item: dict, caregiver_name: str) -> CalendarEvent | None:
    """Pure: one Calendar API event JSON → a busy :class:`CalendarEvent`, or None.

    Returns ``None`` when the event does not block care (cancelled, marked Free,
    or all-day).
    """

    if item.get("status") == "cancelled":
        return None
    if item.get("transparency") == "transparent":  # marked Free, not Busy
        return None

    start = _parse_dt(item.get("start", {}))
    end = _parse_dt(item.get("end", {}))
    if start is None or end is None or start >= end:
        return None  # all-day or malformed → not a timed busy block

    return CalendarEvent(
        title=(item.get("summary") or "(busy)").strip(),
        start=start,
        end=end,
        attendees=(caregiver_name,),
        source_reference=f"gcal_{item.get('id', 'unknown')}",
        origin=FactOrigin.OBSERVED,
    )


class GoogleCalendarConnector:
    """Fetches a caregiver's busy blocks from one Google calendar."""

    def __init__(
        self,
        *,
        caregiver_name: str,
        calendar_id: str = "primary",
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        max_events: int = 500,
        http: httpx.Client | None = None,
    ) -> None:
        if not access_token and not (refresh_token and client_id and client_secret):
            raise ValueError(
                "GoogleCalendarConnector needs an access_token, or refresh_token "
                "+ client_id + client_secret"
            )
        self.caregiver_name = caregiver_name
        self.calendar_id = calendar_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self.max_events = max_events
        self._http = http or httpx.Client(timeout=30)

    # -- auth (mirrors the Gmail connector) ------------------------------------
    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise PermissionError("Calendar access token rejected and no refresh token available")
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
    def fetch_busy(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Busy :class:`CalendarEvent`s for ``[start, end)``, recurrences expanded."""

        events: list[CalendarEvent] = []
        page_token: str | None = None
        url = f"{CALENDAR_API}/calendars/{self.calendar_id}/events"
        while len(events) < self.max_events:
            params: dict = {
                "timeMin": start.isoformat() + "Z" if start.tzinfo is None else start.isoformat(),
                "timeMax": end.isoformat() + "Z" if end.tzinfo is None else end.isoformat(),
                "singleEvents": "true",      # expand recurring events into instances
                "orderBy": "startTime",
                "maxResults": min(250, self.max_events - len(events)),
            }
            if page_token:
                params["pageToken"] = page_token
            listing = self._get(url, params)

            for item in listing.get("items", []) or []:
                event = parse_calendar_event(item, self.caregiver_name)
                if event is not None:
                    events.append(event)
                if len(events) >= self.max_events:
                    break

            page_token = listing.get("nextPageToken")
            if not page_token:
                break
        return events


def fetch_events(*args, **kwargs) -> Iterable[CalendarEvent]:  # pragma: no cover
    """Convenience alias for symmetry with other connectors."""

    return GoogleCalendarConnector(*args, **kwargs).fetch_busy
