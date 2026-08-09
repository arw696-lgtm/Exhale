import React, { useCallback, useEffect, useState } from "react";
import { assignUnattributed, fetchUnattributed } from "../data/api.js";

/**
 * "Who is this for?" — items already in the graph with nobody attached.
 *
 * A photo of one child's season schedule yields events the image never names
 * a person in. Re-uploading can't fix it (identical bytes are fingerprinted
 * as duplicates), so they're assigned where they sit — one tap per child,
 * applied to the whole batch.
 *
 * Silent when there's nothing to assign: an empty state here would just be
 * a chore-shaped hole on the screen.
 */
export default function UnattributedPanel({ familyId, onChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  const load = useCallback(async () => {
    setData(await fetchUnattributed(familyId));
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  const items = data?.items ?? [];
  const children = data?.known_children ?? [];
  if (items.length === 0 || children.length === 0) return null;

  const assign = async (person) => {
    setBusy(true);
    try {
      const body = await assignUnattributed(items.map((i) => i.extraction_id), person, familyId);
      setDone({ person, count: body.assigned });
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
          Who is this for?
        </h2>
      </header>
      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        {items.length} item{items.length === 1 ? "" : "s"} came in without a
        name on them — usually a schedule photo that never said whose it was.
        Assign them and Exhale can reason about who needs to be where.
      </p>

      <ul className="mb-4 max-h-40 space-y-1 overflow-y-auto">
        {items.slice(0, 12).map((i) => (
          <li key={i.extraction_id} className="font-micro text-xs text-sanctuary-navy/55">
            {i.title}
          </li>
        ))}
        {items.length > 12 && (
          <li className="font-micro text-xs text-sanctuary-navy/40">
            …and {items.length - 12} more
          </li>
        )}
      </ul>

      <div className="flex flex-wrap gap-2">
        {children.map((name) => (
          <button
            key={name}
            onClick={() => assign(name)}
            disabled={busy}
            className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
          >
            {busy ? "…" : `All ${name}'s`}
          </button>
        ))}
      </div>
      {done && (
        <p className="mt-3 font-micro text-xs text-sage-release">
          Filed {done.count} under {done.person}.
        </p>
      )}
    </section>
  );
}
