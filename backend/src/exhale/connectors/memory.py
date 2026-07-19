"""In-memory connector (Blueprint §2 Layer 1).

Backs tests and demos, and — importantly — lets externally-fetched batches run
through the exact same pipeline. When an agent/MCP client pulls real Gmail or
Calendar items, it can wrap them as :class:`~exhale.connectors.base.RawMessage`
objects and hand them to a :class:`FixtureConnector`, so "live" ingestion and
fixture ingestion share one code path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from exhale.connectors.base import Connector, RawMessage


class FixtureConnector(Connector):
    channel = "fixture"

    def __init__(self, messages: Iterable[RawMessage]) -> None:
        self._messages = list(messages)

    def fetch(self, since: datetime | None = None) -> Iterable[RawMessage]:
        for msg in sorted(self._messages, key=lambda m: m.received_at):
            if since is None or _aware(msg.received_at) >= _aware(since):
                yield msg


def _aware(dt: datetime) -> datetime:
    from datetime import timezone

    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
