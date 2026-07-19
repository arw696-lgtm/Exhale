import React from "react";

/** Calendar Conflict Resolutions section (Blueprint §9.1). */
export default function CalendarConflicts({ conflicts = [] }) {
  if (conflicts.length === 0) return null;

  return (
    <section className="rounded-card bg-white p-5 shadow-card">
      <header className="mb-4">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ⇌ Calendar Conflict Resolutions
        </h2>
      </header>

      <ul className="space-y-4">
        {conflicts.map((c) => (
          <li key={c.window} className="font-micro text-sm">
            <p className="font-semibold text-sanctuary-navy">{c.window}</p>
            <p className="mt-1 text-sanctuary-navy/70">{c.detail}</p>
            {c.action && (
              <button className="mt-2 rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                → {c.action}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
