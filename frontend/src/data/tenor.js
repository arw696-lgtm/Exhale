/**
 * The week's emotional temperature, said plainly — ONE source of truth shared
 * by the breath glance and the briefing header so the two can never disagree.
 *
 * The tenor rules are honesty rails: a clear week earns "breathe out", a full
 * week gets steadiness ("you've got this"), and nothing here is allowed to
 * wear a party hat while urgent items sit open.
 */
export function weekTenor(briefing) {
  const critical = briefing.summary?.critical_count ?? briefing.critical_threats?.length ?? 0;
  const watch = briefing.summary?.dependency_watch_count ?? briefing.dependency_watch?.length ?? 0;
  const careGaps = briefing.care_watch?.summary?.total_gaps ?? 0;
  const needs = critical + watch;
  const brandNew =
    !briefing.care_watch &&
    (briefing.learned_rules?.length ?? 0) === 0 &&
    needs === 0 &&
    careGaps === 0;

  // Threads being carried for the family — the reassurance number on a quiet
  // week ("N threads are handled or being watched").
  const watched =
    watch +
    (briefing.summary?.advisory_count ?? briefing.advisories?.length ?? 0) +
    (briefing.waiting_on?.summary?.open ?? 0) +
    (briefing.handled?.count ?? 0);

  if (brandNew) {
    return {
      key: "new",
      headline: ["All clear.", "Breathe out."],
      sub: "Connect Gmail or forward a school email, and Exhale starts catching things before they catch you.",
      needs, careGaps, watched, quiet: true, brandNew: true,
    };
  }
  if (needs === 0 && careGaps === 0) {
    return {
      key: "quiet",
      headline: ["A quiet week.", "Nothing needs you."],
      sub: watched > 0
        ? `${watched} thread${watched === 1 ? " is" : "s are"} handled or being watched. Rest easy — we're still listening.`
        : "Nothing needs you right now — a good week to take some time back.",
      needs, careGaps, watched, quiet: true, brandNew: false,
    };
  }
  if (needs <= 2) {
    return {
      key: "lighter",
      headline: ["A lighter week.", "Breathe out."],
      sub: `${needs || "No"} thing${needs === 1 ? "" : "s"} want${needs === 1 ? "s" : ""} you this week. Everything else is handled or watched.`,
      needs, careGaps, watched, quiet: false, brandNew: false,
    };
  }
  return {
    key: "full",
    headline: ["A full week.", "You've got this."],
    sub: `${needs} things want your attention this week — here they are, in order.`,
    needs, careGaps, watched, quiet: false, brandNew: false,
  };
}
