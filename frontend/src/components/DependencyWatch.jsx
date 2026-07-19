import React from "react";

/**
 * Dependency Watch section (Blueprint §7.1, §9.1).
 * Shows the topological validation path: resolved prerequisites plus any
 * unresolved gaps hanging off a confirmed anchor event.
 */
export default function DependencyWatch({ watchItems = [], completed = [] }) {
  return (
    <section className="rounded-card bg-white p-5 shadow-card">
      <header className="mb-4">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ⊟ Dependency Watch
        </h2>
      </header>

      {completed.length === 0 && watchItems.length === 0 && (
        <p className="font-micro text-sm text-sage-release">
          ✓ No open prerequisites — every tracked dependency is clear.
        </p>
      )}

      <ul className="space-y-3">
        {completed.map((c) => (
          <li key={c.title} className="flex items-start gap-3 font-micro text-sm">
            <span className="mt-0.5 text-sage-release">✓</span>
            <span className="text-sanctuary-navy/70">
              <span className="font-semibold text-sanctuary-navy">{c.title}:</span> {c.detail}
            </span>
          </li>
        ))}

        {watchItems.map((w) => (
          <li key={w.obligation_id} className="flex items-start gap-3 font-micro text-sm">
            <span className="mt-0.5 text-looming-amber">▢</span>
            <div className="text-sanctuary-navy">
              <p className="font-semibold">
                {w.title}: <span className="text-looming-amber">{w.status ?? "UNRESOLVED"}</span>
              </p>
              {w.detail && (
                <p className="mt-1 text-sanctuary-navy/70">
                  → {w.detail}{" "}
                  <button className="ml-1 font-semibold text-sage-release underline-offset-2 hover:underline">
                    🛒 Add to Cart
                  </button>
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
