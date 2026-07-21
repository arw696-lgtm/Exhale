"""Live Microsoft Graph calendar connector (Blueprint §1 → Care-Coverage).

The Outlook/Office 365 parallel to the Google Calendar connector: pulls a
caregiver's calendar through Microsoft Graph and maps each *busy* block to a
:class:`~exhale.coverage.CalendarEvent`. Uses Graph's ``calendarView`` endpoint,
which **expands recurring events** into concrete instances server-side within a
window — so weekly meetings come through without client-side RRULE work.

Same honest-defaults discipline as the other connectors: an event the owner is
Free / Working-Elsewhere for (``showAs`` = free/workingElsewhere) doesn't block,
all-day and cancelled events are skipped. Everything mapped is ``OBSERVED``.

Auth mirrors the Google connectors (access token, or the refresh trio against
the Microsoft identity platform token endpoint); ``http`` is injectable and the
mapping is a pure function exercised against real Graph JSON in the tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from exhale.coverage import CalendarEvent
from exhale.schemas import FactOrigin

GRAPH_API = "https://graph.microsoft.com/v1.0"
MSFT_TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
DEFAULT_TZ = "America/Chicago"

# showAs values that mean "not actually busy" → don't block care.
_FREE_STATES = {"free", "workingElsewhere"}


def _parse_graph_dt(node: dict, fallback_tz: ZoneInfo) -> datetime | None:
    """A Graph dateTimeTimeZone → naive local wall-clock datetime.

    Graph returns e.g. ``{"dateTime": "2026-09-19T19:30:00.0000000",
    "timeZone": "America/Chicago"}``. We requested the household tz via the
    ``Prefer`` header, so the wall-clock reading is the dateTime portion.
    """

    raw = node.get("dateTime")
    if not raw:
        return None
    text = raw.split(".")[0]  # drop fractional seconds
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def parse_graph_event(item: dict, caregiver_name: str, *, tz: str = DEFAULT_TZ) -> CalendarEvent | None:
    """Pure: one Graph event JSON → a busy :class:`CalendarEvent`, or None."""

    if item.get("isCancelled"):
        return None
    if item.get("isAllDay"):
        return None
    if (item.get("showAs") or "").strip() in _FREE_STATES:
        return None

    zone = ZoneInfo(tz)
    start = _parse_graph_dt(item.get("start", {}), zone)
    end = _parse_graph_dt(item.get("end", {}), zone)
    if start is None or end is None or start >= end:
        return None

    return CalendarEvent(
        title=(item.get("subject") or "(busy)").strip() or "(busy)",
        start=start,
        end=end,
        attendees=(caregiver_name,),
        source_reference=f"msgraph_{item.get('id', 'unknown')}",
        origin=FactOrigin.OBSERVED,
    )


class GraphCalendarConnector:
    """Fetches a caregiver's busy blocks from an Outlook/Office 365 calendar."""

    def __init__(
        self,
        *,
        caregiver_name: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        tz: str = DEFAULT_TZ,
        max_events: int = 500,
        http: httpx.Client | None = None,
    ) -> None:
        if not access_token and not (refresh_token and client_id and client_secret):
            raise ValueError(
                "GraphCalendarConnector needs an access_token, or refresh_token "
                "+ client_id + client_secret"
            )
        self.caregiver_name = caregiver_name
        self.tz = tz
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self.max_events = max_events
        self._http = http or httpx.Client(timeout=30)

    # -- auth ------------------------------------------------------------------
    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise PermissionError("Graph access token rejected and no refresh token available")
        resp = self._http.post(
            MSFT_TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/Calendars.Read offline_access",
            },
        )
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]

    def _get(self, url: str, params: dict | None) -> dict:
        # NOTE: httpx *replaces* a URL's existing query when `params` is given
        # (even {}), so a nextLink page must be fetched with params=None to keep
        # its cursor. The first page carries its query via `params` instead.
        if self._access_token is None:
            self._refresh_access_token()
        for attempt in (1, 2):
            resp = self._http.get(
                url, params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    # Ask Graph to return times already in the household's zone.
                    "Prefer": f'outlook.timezone="{self.tz}"',
                },
            )
            if resp.status_code == 401 and attempt == 1:
                self._refresh_access_token()
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")

    # -- fetch -----------------------------------------------------------------
    def fetch_busy(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Busy :class:`CalendarEvent`s for ``[start, end)`` (recurrences expanded)."""

        events: list[CalendarEvent] = []
        url: str | None = f"{GRAPH_API}/me/calendarView"
        params: dict | None = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": min(250, self.max_events),
            "$orderby": "start/dateTime",
        }
        while url and len(events) < self.max_events:
            payload = self._get(url, params)
            for item in payload.get("value", []) or []:
                event = parse_graph_event(item, self.caregiver_name, tz=self.tz)
                if event is not None:
                    events.append(event)
                if len(events) >= self.max_events:
                    break
            url = payload.get("@odata.nextLink")
            params = None  # nextLink already carries the full query; keep it
        return events
