import React, { useCallback, useEffect, useState } from "react";
import { applyRetailCleanup, fetchRetailCleanup } from "../data/api.js";

/**
 * Retail notices that reached the graph before Exhale learned to hold them.
 *
 * Shows every item it proposes to clear, by name, and clears nothing until
 * a person taps. Elsewhere Exhale takes junk off a pile unasked, because a
 * wrong call there just leaves something held — here a wrong call would make
 * a real obligation disappear from the week, which is the one thing this
 * product exists to prevent.
 *
 * Silent when there's nothing to clear.
 */
export default function RetailCleanupPanel({ familyId, onChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cleared, setCleared] = useState(null);

  const load = useCallback(async () => {
    setData(await fetchRetailCleanup(familyId));
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  const clear = async () => {
    setBusy(true);
    try {
      const body = await applyRetailCleanup(
        items.map((i) => i.obligation_node_id),
        familyId
      );
      setCleared(body.cleared);
      await load();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-2">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          Tidy up the week
        </h2>
      </header>
      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        {items.length} item{items.length === 1 ? "" : "s"} in your week
        {items.length === 1 ? " looks" : " look"} like a company writing to a
        customer — orders, statements, account notices — rather than something
        the household has to do. Exhale holds these now; these landed before
        it learned to.
      </p>

      <ul className="mb-4 max-h-48 space-y-1 overflow-y-auto">
        {items.map((i) => (
          <li
            key={i.obligation_node_id}
            className="font-micro text-xs text-sanctuary-navy/55"
          >
            {i.title}
          </li>
        ))}
      </ul>

      <button
        onClick={clear}
        disabled={busy}
        className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
      >
        {busy ? "Clearing…" : `Clear ${items.length === 1 ? "it" : "these"}`}
      </button>
      <p className="mt-2 font-micro text-xs text-sanctuary-navy/40">
        They stay in the record — they just stop asking for your week.
      </p>

      {cleared != null && (
        <p className="mt-3 font-micro text-xs text-sage-release">
          Cleared {cleared}. Your week is about your family again.
        </p>
      )}
    </section>
  );
}
