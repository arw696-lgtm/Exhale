import React from "react";
import ThreatCard from "./ThreatCard.jsx";
import DependencyWatch from "./DependencyWatch.jsx";
import CalendarConflicts from "./CalendarConflicts.jsx";
import CareWatch from "./CareWatch.jsx";
import ConnectionsPanel from "./ConnectionsPanel.jsx";
import PhotoDrop from "./PhotoDrop.jsx";
import ReviewQueue from "./ReviewQueue.jsx";
import SetupPanel from "./SetupPanel.jsx";
import WaitingOn from "./WaitingOn.jsx";
import WorkWindowsPanel from "./WorkWindowsPanel.jsx";

/**
 * The Sunday Morning Weekly COO Briefing (Blueprint §9.1).
 * Top-level layout that stitches the three briefing sections together.
 */
export default function WeeklyBriefing({
  briefing,
  drafts = {},
  onOpenDraft,
  user,
  inviteCode,
  onLogout,
  familyId,
  live = false,
  onRefresh,
}) {
  const criticalCount = briefing.summary?.critical_count ?? briefing.critical_threats.length;
  const careGapCount = briefing.care_watch?.summary?.total_gaps ?? 0;
  const isAllClear =
    criticalCount === 0 &&
    careGapCount === 0 &&
    (briefing.dependency_watch?.length ?? 0) === 0 &&
    (briefing.completed?.length ?? 0) === 0 &&
    (briefing.calendar_conflicts?.length ?? 0) === 0;

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:py-12">
      {/* Account row */}
      {user && (
        <div className="mb-4 flex items-center justify-between font-micro text-xs text-sanctuary-navy/60">
          <span>
            {user.display_name}'s household
            {inviteCode && (
              <span className="ml-2 rounded-full bg-sage-release/15 px-2 py-0.5 font-semibold text-sanctuary-navy/70">
                invite code: {inviteCode}
              </span>
            )}
          </span>
          <button onClick={onLogout} className="underline-offset-2 hover:underline">
            Log out
          </button>
        </div>
      )}

      {/* Masthead */}
      <header className="mb-8 flex flex-col gap-1 border-b border-sanctuary-navy/10 pb-6 sm:flex-row sm:items-baseline sm:justify-between">
        <h1 className="font-display text-4xl italic text-sanctuary-navy">Exhale Briefing</h1>
        <p className="font-micro text-sm text-sanctuary-navy/60">{briefing.week_of}</p>
      </header>

      {/* Fresh-household hero */}
      {isAllClear && (
        <section className="mb-8 rounded-card bg-white p-8 text-center shadow-card">
          <p className="font-display text-2xl italic text-sanctuary-navy">
            All clear. Breathe out.
          </p>
          <p className="mx-auto mt-3 max-w-md font-micro text-sm text-sanctuary-navy/60">
            Your household graph is empty so far. Connect Gmail or forward a school
            email, and Exhale will start catching obligations before they catch you.
          </p>
        </section>
      )}

      {/* Critical threats */}
      {criticalCount > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 font-interface text-sm font-semibold uppercase tracking-interface text-looming-amber">
            ⚠ {criticalCount} Critical Threat{criticalCount === 1 ? "" : "s"} Detected
          </h2>
          <div className="space-y-4">
            {briefing.critical_threats.map((item) => {
              const id = item.obligation_id ?? item.obligation_node_id;
              return (
                <ThreatCard
                  key={id}
                  item={item}
                  draft={drafts[id]}
                  onOpenDraft={onOpenDraft}
                />
              );
            })}
          </div>
        </section>
      )}

      {/* Household setup — shown until a coverage model exists */}
      {live && briefing.care_watch == null && (
        <SetupPanel familyId={familyId} onSaved={onRefresh} />
      )}

      {/* Review Queue — items held for a human yes/no (live backend only) */}
      {live && <ReviewQueue familyId={familyId} onChanged={onRefresh} />}

      {/* Care Watch — child-supervision gaps */}
      <CareWatch careWatch={briefing.care_watch} />

      {/* Waiting On — threads where the ball is in someone else's court */}
      {live && <WaitingOn familyId={familyId} />}

      {/* Learned rules — the household's recurring rhythms, with evidence */}
      {(briefing.learned_rules?.length ?? 0) > 0 && (
        <section className="mb-8 rounded-card bg-white p-5 shadow-card">
          <h2 className="mb-3 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
            🧠 Patterns Exhale Has Learned
          </h2>
          <ul className="space-y-2">
            {briefing.learned_rules.map((rule) => (
              <li key={rule.kind + rule.subject} className="border-l-2 border-sage-release/60 pl-3 font-micro text-sm text-sanctuary-navy/80">
                {rule.detail}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Photo ingestion + work windows (live backend only) */}
      {live && <PhotoDrop familyId={familyId} onChanged={onRefresh} />}
      {live && <WorkWindowsPanel familyId={familyId} />}

      {/* Connections — Connect Google / Outlook (logged-in households) */}
      {user && <ConnectionsPanel familyId={user.family_id} />}

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
