/**
 * Say who is actually in this household, by name.
 *
 * The app was written assuming a shape: two parents, more than one child.
 * "While you've got the kids", "Children who need supervision", "Both parents
 * at a concert" — all hardcoded, all shown to a household with one child, who
 * reasonably asked why an app he had just told about his family was talking
 * about kids plural.
 *
 * It reads as carelessness, and for anyone whose household is not the assumed
 * shape — one child, one parent, a grandparent raising a grandchild, a carer
 * who is not a parent — it reads as "this was not built for you". That matters
 * more, not less, for something meant to be shared.
 *
 * The fix follows a rule the product already holds elsewhere: names, never
 * counts. "While you've got Stevie" is more accurate than "the kids", and
 * warmer, and it costs nothing — the household has already told us the names.
 * Past two names a list stops being readable, so a collective word takes over.
 */

/** Every child the coverage model knows, in order. */
export function childNames(briefing) {
  const watch = briefing?.care_watch;
  const named = watch?.recipients ?? (watch?.recipient ? [watch.recipient] : []);
  return named.filter(Boolean);
}

/** "Stevie" · "Stevie and Leo" · "Stevie, Leo and Ada" */
export function nameList(names) {
  const list = (names ?? []).filter(Boolean);
  if (list.length === 0) return "";
  if (list.length === 1) return list[0];
  if (list.length === 2) return `${list[0]} and ${list[1]}`;
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

/**
 * How to refer to the children in running copy.
 *
 * One or two: their names. Three or more: "the kids", where the plural is
 * true. No household configured yet: "the kids", which is the only honest
 * option when we have not been told anything.
 */
export function childrenPhrase(briefing, { fallback = "the kids" } = {}) {
  const names = childNames(briefing);
  if (names.length === 0) return fallback;
  if (names.length <= 2) return nameList(names);
  return fallback;
}

/** True when the household has exactly one child — for verb agreement. */
export function isSingleChild(briefing) {
  return childNames(briefing).length === 1;
}

/**
 * "Stevie is looked after" vs "the kids are looked after".
 * Subject and verb have to travel together or one of them will be wrong.
 */
export function childrenAre(briefing) {
  return isSingleChild(briefing) ? "is" : "are";
}

/** "Stevie needs someone" vs "the kids need someone". */
export function childrenVerb(briefing, singular, plural) {
  return isSingleChild(briefing) ? singular : plural;
}
