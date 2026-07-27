import React from "react";
import WhyTrace from "./WhyTrace.jsx";

/**
 * Dependency Watch (Blueprint §7.1, §9.1) — the quiet vocabulary.
 *
 * The prerequisites hanging off confirmed events: what's satisfied (a sage
 * check) and what's still open (a soft amber dot, "still open" not
 * "UNRESOLVED"). Attention without alarm, matching the rest of the page.
 */
export default function DependencyWatch({ watchItems = [], completed = [] }) {
  if (completed.length === 0 && watchItems.length === 0) {
    return (
      <section className="rounded-[22px] border border-sanctuary-navy/10 bg-white p-5 shadow-card">
        <h2 className="mb-3 font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
          Dependency watch
        </h2>
        <p className="font-micro text-sm text-sanctuary-navy/55">
          Every tracked prerequisite is clear.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-[22px] border border-sanctuary-navy/10 bg-white p-5 shadow-card">
      <h2 className="mb-4 font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
        Dependency watch
      </h2>

      <ul className="space-y-3">
        {completed.map((c) => (
          <li key={c.title} className="flex items-start gap-3 font-micro text-sm">
            <span className="mt-0.5 grid h-[18px] w-[18px] flex-none place-items-center rounded-full bg-sage-release/15 text-[11px] font-bold text-sage-release">
              ✓
            </span>
            <span className="text-sanctuary-navy/70">
              <span className="font-semibold text-sanctuary-navy">{c.title}:</span> {c.detail}
            </span>
          </li>
        ))}

        {watchItems.map((w) => (
          <li key={w.obligation_id} className="flex items-start gap-3 font-micro text-sm">
            <span className="severity-dot severity-dot--amber mt-[7px]" aria-hidden="true" />
            <div className="text-sanctuary-navy">
              <p className="font-semibold">
                {w.title}
                <span className="ml-2 font-medium text-sanctuary-navy/50">still open</span>
              </p>
              {w.detail && (
                <p className="mt-1 text-sanctuary-navy/70">
                  {w.detail}{" "}
                  <button className="ml-1 font-semibold text-sage-release underline-offset-2 hover:underline">
                    Add to cart
                  </button>
                </p>
              )}
              <WhyTrace why={w.why} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
