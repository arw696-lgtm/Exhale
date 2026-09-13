import React, { useCallback, useEffect, useState } from "react";
import {
  assignUnattributed,
  fetchUnattributed,
  leaveUnattributedAlone,
} from "../data/api.js";

/**
 * "Who is this for?" — one card per schedule photo.
 *
 * Deliberately scoped to photos, one batch at a time. A season schedule is
 * one child's, so "all of these are Stevie's" is a true statement about it.
 * The inbox is not: a bank statement and a parent's work meeting have no
 * child, and that is the correct answer rather than a gap to fill. An
 * earlier version pooled everything behind a single button and would have
 * filed 227 mixed items — work meetings included — under a kid.
 *
 * Silent when there's nothing to ask about.
 */
export default function UnattributedPanel({ familyId, onChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null); // source_reference being acted on
  const [done, setDone] = useState(null);

  const load = useCallback(async () => {
    setData(await fetchUnattributed(familyId));
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  const groups = data?.groups ?? [];
  const children = data?.known_children ?? [];
  if (groups.length === 0 || children.length === 0) return null;

  const act = async (group, fn, message) => {
    setBusy(group.source_reference);
    try {
      await fn(group.items.map((i) => i.extraction_id));
      setDone(message);
      await load();
      onChanged?.();
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-2">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          Who is this for?
        </h2>
      </header>
      <p className="mb-4 font-micro text-sm text-sanctuary-navy/60">
        These came off a photo that never said whose schedule it was. Name the
        batch and Exhale can reason about who needs to be where.
      </p>

      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.source_reference} className="rounded-2xl bg-pure-breath p-4">
            <p className="font-micro text-sm font-medium text-sanctuary-navy/85">
              {g.source}
              <span className="ml-2 font-normal text-sanctuary-navy/45">
                {g.count} item{g.count === 1 ? "" : "s"}
              </span>
            </p>
            <ul className="mt-2 space-y-0.5">
              {g.items.slice(0, 4).map((i) => (
                <li
                  key={i.extraction_id}
                  className="font-micro text-xs text-sanctuary-navy/55"
                >
                  {i.title}
                </li>
              ))}
              {g.count > 4 && (
                <li className="font-micro text-xs text-sanctuary-navy/40">
                  …and {g.count - 4} more
                </li>
              )}
            </ul>

            <div className="mt-3 flex flex-wrap gap-2">
              {children.map((name) => (
                <button
                  key={name}
                  onClick={() =>
                    act(
                      g,
                      (ids) => assignUnattributed(ids, name, familyId),
                      `Filed ${g.count} under ${name}.`
                    )
                  }
                  disabled={busy === g.source_reference}
                  className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
                >
                  {busy === g.source_reference ? "…" : `All ${name}'s`}
                </button>
              ))}
              <button
                onClick={() =>
                  act(
                    g,
                    (ids) => leaveUnattributedAlone(ids, familyId),
                    "Left as they are."
                  )
                }
                disabled={busy === g.source_reference}
                className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-micro text-sm text-sanctuary-navy transition hover:bg-surface disabled:opacity-50"
              >
                Not one person's
              </button>
            </div>
          </div>
        ))}
      </div>

      {done && (
        <p className="mt-3 font-micro text-xs text-sage-release">{done}</p>
      )}
    </section>
  );
}
