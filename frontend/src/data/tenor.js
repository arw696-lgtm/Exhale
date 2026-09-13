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
  // Has Exhale read anything at all? Every count below is zero both when the
  // week is genuinely clear and when nothing has ever been read, and only
  // this tells them apart. A household that has just started over has its
  // coverage model and its people intact, so the old brandNew test (no
  // care_watch) reads it as an ordinary quiet week and says "nothing needs
  // you" about mail it has not opened. That is the one thing an instrument
  // like this must never say. Undefined on an older payload or the offline
  // fixture, which must keep their existing behaviour.
  const read = briefing.summary?.artifacts_read;
  const nothingRead = read === 0;
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

  // Checked before every other state: an empty system must never report calm.
  // "All clear" below is a finding — it means Exhale looked. This means it
  // hasn't, and the only honest thing to do is say so and point at the fix.
  if (nothingRead) {
    return {
      key: "unread",
      headline: ["Nothing read", "yet."],
      sub: "Exhale hasn't read any of your mail. Open Household → Connections and tap “Scan my email now” — this is silence, not calm.",
      needs, careGaps, watched, quiet: false, brandNew: true,
    };
  }
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
