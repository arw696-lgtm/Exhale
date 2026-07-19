import React from "react";
import ThreatCard from "./ThreatCard.jsx";
import DependencyWatch from "./DependencyWatch.jsx";
import CalendarConflicts from "./CalendarConflicts.jsx";

/**
 * The Sunday Morning Weekly COO Briefing (Blueprint §9.1).
 * Top-level layout that stitches the three briefing sections together.
 */
export default function WeeklyBriefing({ briefing }) {
  const criticalCount = briefing.summary?.critical_count ?? briefing.critical_threats.length;

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:py-12">
      {/* Masthead */}
      <header className="mb-8 flex flex-col gap-1 border-b border-sanctuary-navy/10 pb-6 sm:flex-row sm:items-baseline sm:justify-between">
        <h1 className="font-display text-4xl italic text-sanctuary-navy">Exhale Briefing</h1>
        <p className="font-micro text-sm text-sanctuary-navy/60">{briefing.week_of}</p>
      </header>

      {/* Critical threats */}
      {criticalCount > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 font-interface text-sm font-semibold uppercase tracking-interface text-looming-amber">
            ⚠ {criticalCount} Critical Threat{criticalCount === 1 ? "" : "s"} Detected
          </h2>
          <div className="space-y-4">
            {briefing.critical_threats.map((item) => (
              <ThreatCard key={item.obligation_id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Dependency watch */}
      <div className="mb-8">
        <DependencyWatch
          watchItems={briefing.dependency_watch}
          completed={briefing.completed}
        />
      </div>

      {/* Calendar conflicts */}
      <CalendarConflicts conflicts={briefing.calendar_conflicts} />

      <footer className="mt-10 text-center font-micro text-xs text-sanctuary-navy/40">
        Take a deep breath — your memory systems are secure.
      </footer>
    </main>
  );
}
