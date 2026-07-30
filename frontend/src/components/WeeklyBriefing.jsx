import React from "react";
import BreathHeader from "./BreathHeader.jsx";
import ThreatCard from "./ThreatCard.jsx";
import DependencyWatch from "./DependencyWatch.jsx";
import CalendarConflicts from "./CalendarConflicts.jsx";
import CareWatch from "./CareWatch.jsx";
import HandledRecap from "./HandledRecap.jsx";
import ReviewQueue from "./ReviewQueue.jsx";
import TasksPanel from "./TasksPanel.jsx";
import TimeForWhatMatters from "./TimeForWhatMatters.jsx";
import WaitingOn from "./WaitingOn.jsx";

/**
 * Today — the Weekly COO Briefing (Blueprint §9.1), the app's home tab.
 *
 * Reads like a person thinks: open with a breath, then only what needs you,
 * then your time, and close on relief. The setup/connection plumbing lives in
 * the Household and You tabs so this screen stays about the week.
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
  onOpenReview,
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

      {/* Quiet doorway to the look-back — leads on Sunday, one tap any day. */}
      {onOpenReview && (
        <div className="-mt-2 mb-6 text-center">
          <button
            onClick={onOpenReview}
            className="font-micro text-xs font-medium text-sage-release transition hover:text-sanctuary-navy"
          >
            Your week, in review →
          </button>
        </div>
      )}

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

      {/* Around the house — the family's own task pile, laid next to found time */}
      {live && (
        <TasksPanel
          familyId={familyId}
          window={briefing.time_for_what_matters?.windows?.[0]}
          onChanged={onRefresh}
        />
      )}

      {/* Review Queue — items held for a human yes/no (live backend only) */}
      {live && <ReviewQueue familyId={familyId} onChanged={onRefresh} />}

      {/* Care Watch — child-supervision gaps */}
      <CareWatch careWatch={briefing.care_watch} familyId={familyId} live={live} />

      {/* Waiting On — threads where the ball is in someone else's court */}
      {live && <WaitingOn familyId={familyId} />}

      {/* Learned rules — the household's recurring rhythms, with evidence */}
      {(briefing.learned_rules?.length ?? 0) > 0 && (
        <section className="mb-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
          <h2 className="mb-3 font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
            Patterns Exhale has learned
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
