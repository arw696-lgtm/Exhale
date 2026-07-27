import React from "react";
import BreathHeader from "./BreathHeader.jsx";
import ThreatCard from "./ThreatCard.jsx";
import DependencyWatch from "./DependencyWatch.jsx";
import CalendarConflicts from "./CalendarConflicts.jsx";
import CareWatch from "./CareWatch.jsx";
import ConnectionsPanel from "./ConnectionsPanel.jsx";
import HandledRecap from "./HandledRecap.jsx";
import HelperInvitePanel from "./HelperInvitePanel.jsx";
import PhotoDrop from "./PhotoDrop.jsx";
import ReviewQueue from "./ReviewQueue.jsx";
import SetupPanel from "./SetupPanel.jsx";
import TimeForWhatMatters from "./TimeForWhatMatters.jsx";
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

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:py-12">
      {/* Open with a breath — the week's temperature, said plainly. */}
      <BreathHeader
        user={user}
        briefing={briefing}
        inviteCode={inviteCode}
        onLogout={onLogout}
      />

      {/* Needs you — the short list of what actually wants attention. */}
      {criticalCount > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 flex items-center gap-2 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
            <span className="severity-dot severity-dot--amber" aria-hidden="true" />
            Needs you · {criticalCount}
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

      {/* Time For What Matters — the emotional heart, right after what needs you:
          your time (alone / together / on-duty) next to what it's for. */}
      <TimeForWhatMatters
        block={briefing.time_for_what_matters}
        familyId={familyId}
        live={live}
        onRefresh={onRefresh}
      />

      {/* Household setup — shown until a coverage model exists */}
      {live && briefing.care_watch == null && (
        <SetupPanel familyId={familyId} onSaved={onRefresh} />
      )}

      {/* Review Queue — items held for a human yes/no (live backend only) */}
      {live && <ReviewQueue familyId={familyId} onChanged={onRefresh} />}

      {/* Care Watch — child-supervision gaps */}
      <CareWatch careWatch={briefing.care_watch} familyId={familyId} live={live} />

      {/* Waiting On — threads where the ball is in someone else's court */}
      {live && <WaitingOn familyId={familyId} />}

      {/* Learned rules — the household's recurring rhythms, with evidence */}
      {(briefing.learned_rules?.length ?? 0) > 0 && (
        <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
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

      {/* Helpers — invite/scope a secondary caregiver (members, live backend) */}
      {live && user && <HelperInvitePanel familyId={familyId} />}

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

      {/* Closing note — what resolved this week, so the family didn't carry it */}
      <HandledRecap handled={briefing.handled} />

      <footer className="mt-10 text-center font-micro text-xs text-sanctuary-navy/40">
        Take a deep breath — your memory systems are secure.
      </footer>
    </main>
  );
}
