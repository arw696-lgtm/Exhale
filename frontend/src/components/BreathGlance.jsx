import React from "react";
import ThemeToggle from "./ThemeToggle.jsx";
import { weekTenor } from "../data/tenor.js";

/**
 * The Breath Glance — the app's opening state, and where most opens should
 * END. One full screen: the breath, the time, the week's temperature in a
 * sentence, and only what needs you. Everything else lives one gesture below.
 *
 * This is set-it-and-forget-it made visible: three seconds, breathe out,
 * pocket the phone. The tenor comes from the same honesty rails as the
 * briefing (weekTenor) — a behind week can never say "breathe out" here.
 */
function timeLabel() {
  const d = new Date();
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const h = d.getHours();
  const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
  return `${day} ${part}`;
}

function shortDay(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
}

export default function BreathGlance({
  briefing,
  drafts = {},
  user,
  inviteCode,
  onLogout,
  onOpenDraft,
  onOpenReview,
  detailId = "week-detail",
}) {
  const tenor = weekTenor(briefing);
  const first = user?.display_name?.trim().split(/\s+/)[0];
  const isSunday = new Date().getDay() === 0;
  const items = (briefing.critical_threats ?? []).slice(0, 3);

  const reveal = () => {
    document.getElementById(detailId)?.scrollIntoView({ behavior: "smooth" });
  };

  const openItem = (item) => {
    const id = item.obligation_id ?? item.obligation_node_id;
    if (drafts[id]) onOpenDraft?.(id);
    else reveal(); // no draft yet — the full card explains itself below
  };

  return (
    <section
      className="relative flex flex-col px-6"
      style={{ minHeight: "100dvh" }} /* the opening viewport is ONLY the glance */
    >
      {/* top bar — household left, theme + logout right */}
      <div className="flex items-center justify-between pt-5 font-micro text-xs text-sanctuary-navy/50">
        <span>
          {user ? (
            <>
              {user.display_name}'s household
              {inviteCode && (
                <span className="ml-2 rounded-full bg-sage-release/15 px-2 py-0.5 font-semibold text-sanctuary-navy/60">
                  invite: {inviteCode}
                </span>
              )}
            </>
          ) : (
            <span aria-hidden="true">&nbsp;</span>
          )}
        </span>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          {user && onLogout && (
            <button onClick={onLogout} className="ml-1 underline-offset-2 hover:underline">
              Log out
            </button>
          )}
        </div>
      </div>

      {/* the glance — centered breath, tenor, and only what needs you */}
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <div
          aria-hidden="true"
          className="breath-orb h-52 w-52 rounded-full sm:h-60 sm:w-60"
          style={{
            background:
              "radial-gradient(circle at 42% 42%, rgb(var(--sage) / 0.42), rgb(var(--sage) / 0.10) 55%, transparent 70%)",
            filter: "blur(6px)",
          }}
        />

        <p className="mt-7 font-interface text-[11px] font-semibold uppercase tracking-[0.2em] text-sanctuary-navy/45">
          {timeLabel()}
          {first && ` · ${first}`}
        </p>

        <h1 className="mt-3 font-display text-[2.4rem] italic leading-[1.08] text-sanctuary-navy sm:text-[2.7rem]">
          {tenor.headline[0]}
          <br />
          {tenor.headline[1]}
        </h1>

        <p className="mx-auto mt-4 max-w-[19.5rem] font-micro text-sm leading-relaxed text-sanctuary-navy/55">
          {tenor.sub}
        </p>

        {/* needs-you rows — each a doorway into acting on it */}
        {items.length > 0 && (
          <ul className="mt-8 w-full max-w-xs space-y-1 text-left">
            {items.map((item) => {
              const id = item.obligation_id ?? item.obligation_node_id;
              return (
                <li key={id}>
                  <button
                    onClick={() => openItem(item)}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 font-micro text-sm text-sanctuary-navy/85 transition hover:bg-surface/70"
                  >
                    <span className="severity-dot severity-dot--amber" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{item.title}</span>
                    {item.deadline && (
                      <span className="shrink-0 text-xs text-looming-amber">
                        {shortDay(item.deadline)}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
            {tenor.needs > items.length && (
              <li className="px-3 pt-1 text-center font-micro text-xs text-sanctuary-navy/40">
                and {tenor.needs - items.length} more below
              </li>
            )}
          </ul>
        )}

        {/* quiet week — reassurance answers "…are you sure?" with evidence */}
        {tenor.quiet && !tenor.brandNew && (
          <button
            onClick={reveal}
            className="mt-8 rounded-full border border-sanctuary-navy/15 px-5 py-2.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-surface"
          >
            See what's handled →
          </button>
        )}

        {/* Sunday — the glance opens into the look-back */}
        {isSunday && onOpenReview && (
          <button
            onClick={onOpenReview}
            className="mt-4 font-micro text-xs font-medium text-sage-release transition hover:text-sanctuary-navy"
          >
            Your week, in review →
          </button>
        )}
      </div>

      {/* the doorway to the full week — padded clear of the floating tab bar */}
      <div className="pb-24 text-center">
        <button
          onClick={reveal}
          className="font-micro text-xs text-sanctuary-navy/40 transition hover:text-sanctuary-navy/70"
          aria-label="See the full week"
        >
          see the full week ↓
        </button>
      </div>
    </section>
  );
}
