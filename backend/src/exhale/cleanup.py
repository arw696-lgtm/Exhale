"""Clearing retail notices that already reached the graph.

:mod:`exhale.relevance` stops new ones from committing. This clears the ones
that landed before that rule existed — on a real household, most of the 35
auto-commits whose corrections dragged the trust ledger to 43%.

Two deliberate choices:

**Proposed, never automatic.** Everywhere else the machine may take junk off
a pile unasked, because the failure mode is benign: a held item stays held.
Here it isn't. Removing something from the graph means it stops appearing in
the briefing, and a wrong call makes a real obligation vanish silently — the
one thing this product exists to prevent. So the sweep shows its work and a
person taps.

**Closed, not deleted.** The obligation keeps every property and the ledger
entry is untouched; only ``status`` changes. NOT_RELEVANT is its own status
rather than COMPLETED because nothing was completed — and clearing junk is
not an accomplishment, so this never reaches the handled recap. Letting go
is a release, not a win.
"""

from __future__ import annotations

from exhale.graph import NodeType
from exhale.relevance import is_transactional_notice

# Its own status so the record stays honest about what happened. Listed in
# the engine's resolved set, so these stop surfacing as gaps.
NOT_RELEVANT = "NOT_RELEVANT"

_ALREADY_CLOSED = {"CLEAR", "COMPLETED", "RESOLVED", "CONFIRMED", NOT_RELEVANT}


def find_committed_noise(store, family_id: str) -> list[dict]:
    """Open obligations in the graph that read as a company's notification."""

    graph = store.graph(family_id)
    found = []
    for node in graph.nodes.values():
        if node.type is not NodeType.OBLIGATION:
            continue
        if str(node.properties.get("status", "")).upper() in _ALREADY_CLOSED:
            continue
        name = str(node.properties.get("name") or "")
        if not is_transactional_notice(name):
            continue
        found.append({
            "obligation_node_id": node.node_id,
            "title": name,
            "deadline": node.properties.get("deadline"),
            "source": node.properties.get("source_document_name"),
        })
    found.sort(key=lambda i: (i["deadline"] or "", i["title"]))
    return found


def clear_committed_noise(store, family_id: str, node_ids: list[str]) -> int:
    """Close the named obligations as NOT_RELEVANT. Returns how many changed.

    Only clears nodes that still read as transactional — an id that no longer
    qualifies (edited since, or never did) is skipped rather than trusted, so
    a stale request from an old screen can't close something real.
    """

    wanted = set(node_ids)
    cleared = 0
    with store.family_lock(family_id):
        graph = store.graph(family_id)
        for node_id in wanted:
            node = graph.nodes.get(node_id)
            if node is None or node.type is not NodeType.OBLIGATION:
                continue
            if str(node.properties.get("status", "")).upper() in _ALREADY_CLOSED:
                continue
            if not is_transactional_notice(str(node.properties.get("name") or "")):
                continue
            node.properties["status"] = NOT_RELEVANT
            cleared += 1
        if cleared:
            store.set_graph(family_id, graph)
    return cleared
