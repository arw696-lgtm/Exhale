"""Layer 1 — Data Collection connectors (Blueprint §2, §6).

Connectors pull raw, unstructured items from a household's messy multi-channel
pipelines (email, calendar feeds, uploaded documents) and yield normalized
:class:`~exhale.connectors.base.RawMessage` objects. The extraction layer
(:mod:`exhale.extraction`) then turns those into schema-validated
:class:`~exhale.schemas.ExtractionPayload` contracts.

Concrete connectors:

* :class:`~exhale.connectors.memory.FixtureConnector` — in-memory source for
  tests, demos, and feeding externally-fetched batches (e.g. via an MCP client)
  through the same pipeline.
* :class:`~exhale.connectors.imap.ImapConnector` — reference IMAP/email source
  built on the standard library.
"""

from exhale.connectors.base import Attachment, Connector, RawMessage
from exhale.connectors.memory import FixtureConnector

__all__ = ["Attachment", "Connector", "RawMessage", "FixtureConnector"]
