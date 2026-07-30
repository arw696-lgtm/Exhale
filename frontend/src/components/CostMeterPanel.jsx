import React, { useEffect, useState } from "react";
import { fetchCosts } from "../data/api.js";

/**
 * Running Costs — the Milo lesson as a panel. Shows what this household's AI
 * actually costs to run: this week, and the monthly pace once a full week has
 * been observed. Most extractions never touch the API (the deterministic
 * engine is free), so a cheap week honestly reads as cheap — and a zero week
 * reads as zero.
 */
function usd(n) {
  if (n == null) return null;
  if (n === 0) return "$0";
  if (n < 0.01) return "<$0.01";
  return `$${n.toFixed(2)}`;
}

export default function CostMeterPanel({ familyId }) {
  const [meter, setMeter] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCosts(familyId).then((m) => alive && setMeter(m));
    return () => {
      alive = false;
    };
  }, [familyId]);

  if (!meter) return null;

  const { week, all_time, projected_monthly_usd } = meter;

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <h2 className="mb-3 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
        Running costs
      </h2>
      {all_time.calls === 0 ? (
        <p className="font-micro text-sm text-sanctuary-navy/55">
          No AI spend yet — everything so far ran on the free deterministic
          engine. When Exhale does call its AI (reading a tricky email, a
          photo), the real cost shows here.
        </p>
      ) : (
        <>
          <div className="flex items-baseline gap-6">
            <div>
              <p className="font-display text-2xl italic text-sanctuary-navy">
                {usd(week.estimated_cost_usd)}
              </p>
              <p className="font-micro text-xs text-sanctuary-navy/45">
                this week · {week.calls} AI call{week.calls === 1 ? "" : "s"}
              </p>
            </div>
            {projected_monthly_usd != null && (
              <div>
                <p className="font-display text-2xl italic text-sanctuary-navy/80">
                  {usd(projected_monthly_usd)}
                </p>
                <p className="font-micro text-xs text-sanctuary-navy/45">
                  monthly pace
                </p>
              </div>
            )}
          </div>
          <p className="mt-3 font-micro text-xs text-sanctuary-navy/40">
            Planning estimates from real token counts · {all_time.calls} calls
            all time ({usd(all_time.estimated_cost_usd)}). Routine extractions
            are free — only AI-assisted reads cost anything.
          </p>
        </>
      )}
    </section>
  );
}
