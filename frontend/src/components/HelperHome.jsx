import React, { useEffect, useState } from "react";
import { threatPresentation } from "../brand/tokens.js";
import { fetchHelperView } from "../data/api.js";

/**
 * Helper Home — the entire experience for a scoped caregiver (FAMILY_STRUCTURES
 * §3.2). A grandparent or regular sitter invited for specific days sees only
 * their care days' gaps and the items the household explicitly shared — never
 * the briefing, the inbox-derived obligations, or another day's data.
 *
 * This is deliberately its own screen, not a trimmed briefing: a helper isn't a
 * lesser member, they're a different relationship. The copy says so.
 */
function formatWindow(gap) {
  const day = new Date(gap.start).toLocaleDateString(undefined, {
    weekday: "long", month: "short", day: "numeric",
  });
  const time = (iso) =>
    new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${time(gap.start)}–${time(gap.end)}`;
}

export default function HelperHome({ familyId, displayName, onLogout }) {
  const [view, setView] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchHelperView(familyId).then((v) => {
      if (!alive) return;
      setView(v);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [familyId]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="font-display text-2xl italic text-sanctuary-navy/50">
          Loading your days…
        </p>
      </div>
    );
  }

  const care = view?.care_watch ?? { gaps: [], summary: {} };
  const shared = view?.shared_obligations ?? [];
  const days = view?.scope?.covered_weekdays ?? [];
  const recipient = care.recipient || "the family";

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="font-display text-3xl text-sanctuary-navy">
            {displayName ? `Hi, ${displayName}` : "Your care days"}
          </h1>
          <p className="mt-1 font-micro text-sm text-sanctuary-navy/60">
            {days.length
              ? `Helping with ${recipient} on ${days.join(" & ")}.`
              : "No care days assigned yet — the family will set these up."}
          </p>
        </div>
        {onLogout && (
          <button onClick={onLogout}
            className="font-micro text-xs text-sanctuary-navy/50 underline hover:text-sanctuary-navy/80">
            Sign out
          </button>
        )}
      </header>

      <section className="mb-8 rounded-card bg-white p-5 shadow-card">
        <h2 className="mb-4 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🧑‍🍼 Care needed on your days
        </h2>
        {care.gaps.length === 0 ? (
          <p className="font-micro text-sm text-sanctuary-navy/50">
            Nothing needs covering on your days right now. You're all set.
          </p>
        ) : (
          <ul className="space-y-4">
            {care.gaps.map((gap) => {
              const band = threatPresentation[gap.threat_level] ?? threatPresentation.ADVISORY;
              return (
                <li key={`${gap.start}-${gap.end}`}
                    className="border-l-2 pl-3 font-micro text-sm"
                    style={{ borderColor: band.accent }}>
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="font-semibold text-sanctuary-navy">
                      {band.indicator} {formatWindow(gap)}
                    </p>
                    <span className="whitespace-nowrap text-xs text-sanctuary-navy/50">
                      {gap.duration_hours}h
                    </span>
                  </div>
                  <p className="mt-1 text-sanctuary-navy/70">{gap.reason}</p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {shared.length > 0 && (
        <section className="mb-8 rounded-card bg-white p-5 shadow-card">
          <h2 className="mb-4 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
            📌 Shared with you
          </h2>
          <ul className="space-y-3">
            {shared.map((ob) => (
              <li key={ob.obligation_id} className="font-micro text-sm">
                <p className="font-semibold text-sanctuary-navy">{ob.title}</p>
                <p className="mt-0.5 text-sanctuary-navy/60">
                  {[ob.person, ob.date && new Date(ob.date).toLocaleDateString(undefined, {
                    month: "short", day: "numeric",
                  })].filter(Boolean).join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-center font-micro text-xs text-sanctuary-navy/40">
        You see only your care days and what the family shares — nothing else.
      </p>
    </main>
  );
}
