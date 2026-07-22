import React from "react";

/**
 * What Exhale Handled This Week — the briefing's closing note.
 *
 * Relief, not achievement-bragging: the point isn't that the software did
 * things, it's that the family didn't have to carry them. Renders only real
 * entries from the resolved-items log; a quiet week says so honestly and a
 * missing log (offline fixture) renders nothing.
 */
const TYPE_ICON = {
  dependency_gap: "✓",
  waiting_on: "↩",
  pattern_catch: "🧠",
};

function fmtDay(iso) {
  return new Date(iso).toLocaleDateString(undefined, { weekday: "long" });
}

export default function HandledRecap({ handled }) {
  if (!handled) return null; // log not supplied (offline preview) — no section

  const { count, items } = handled;

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <h2 className="mb-3 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
        🌬 What Exhale Handled This Week
      </h2>
      {count === 0 ? (
        <p className="font-micro text-sm text-sanctuary-navy/60">
          A quiet week — nothing needed catching.
        </p>
      ) : (
        <>
          <p className="mb-3 font-micro text-sm text-sanctuary-navy/70">
            {count} thing{count === 1 ? "" : "s"} got sorted so you didn't have
            to carry {count === 1 ? "it" : "them"}:
          </p>
          <ul className="space-y-2">
            {items.map((e) => (
              <li
                key={`${e.resolved_type}-${e.item_id}`}
                className="flex items-baseline gap-2 border-l-2 border-sage-release/50 pl-3 font-micro text-sm text-sanctuary-navy/80"
              >
                <span className="text-sage-release" aria-hidden="true">
                  {TYPE_ICON[e.resolved_type] ?? "✓"}
                </span>
                <span>
                  {e.brief_description}
                  <span className="ml-2 text-xs text-sanctuary-navy/40">
                    {fmtDay(e.resolved_at)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
