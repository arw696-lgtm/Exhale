import React, { useRef, useState } from "react";
import { attributeExtraction, uploadPhoto, uploadSchoolCalendar } from "../data/api.js";

/**
 * Photo Drop — "just screenshot it and add it in."
 *
 * Two deliberately separate doors, because they mean different things:
 *
 * • Events (flyers, sports schedules) become individual tracked items.
 * • A school-year calendar becomes that child's SCHOOL CALENDAR — its
 *   no-school days flip care from "school has them" to "we do." Sending one
 *   through the events door turns a year of teacher workshops into forty
 *   things to confirm, which is the opposite of useful.
 *
 * When a photo yields items Exhale can't attribute to anyone, it asks rather
 * than guessing — a wrong child is worse than an unassigned one.
 */
export default function PhotoDrop({ familyId, knownChildren = [], onChanged }) {
  const inputRef = useRef(null);
  const schoolRef = useRef(null);
  const [progress, setProgress] = useState(null); // {done, total} while busy
  const [result, setResult] = useState(null); // {items, failures, children, unattributed}
  const [schoolResult, setSchoolResult] = useState(null);
  const [attributing, setAttributing] = useState(false);
  const [schoolChild, setSchoolChild] = useState(knownChildren[0] ?? "");
  const [error, setError] = useState(null);

  const busy = progress !== null;

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList ?? []);
    if (files.length === 0) return;
    setError(null);
    setResult(null);
    setSchoolResult(null);
    setProgress({ done: 0, total: files.length });

    const items = [];
    const failures = [];
    let children = knownChildren;
    let unattributed = [];
    let anyOk = false;
    for (const [index, file] of files.entries()) {
      setProgress({ done: index, total: files.length });
      try {
        const body = await uploadPhoto(file, familyId, knownChildren);
        anyOk = true;
        items.push(...(body.items ?? []));
        if (body.known_children?.length) children = body.known_children;
        unattributed = unattributed.concat(body.unattributed ?? []);
      } catch (e) {
        if (e.message.includes("not configured")) {
          setError(
            "Photo reading isn't set up on this server yet (needs an Anthropic key)."
          );
          setProgress(null);
          if (inputRef.current) inputRef.current.value = "";
          return;
        }
        failures.push({ name: file.name || `photo ${index + 1}`, message: e.message });
      }
    }

    setResult({ items, failures, children, unattributed });
    setProgress(null);
    if (inputRef.current) inputRef.current.value = "";
    if (anyOk) onChanged?.();
  };

  const attributeAll = async (childName) => {
    if (!result?.unattributed?.length) return;
    setAttributing(true);
    setError(null);
    try {
      for (const id of result.unattributed) {
        await attributeExtraction(id, childName, familyId);
      }
      setResult({ ...result, unattributed: [], attributedTo: childName });
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setAttributing(false);
    }
  };

  const handleSchool = async (file) => {
    if (!file) return;
    if (!schoolChild) {
      setError("Pick whose school calendar this is first.");
      return;
    }
    setError(null);
    setResult(null);
    setSchoolResult(null);
    setProgress({ done: 0, total: 1 });
    try {
      setSchoolResult(await uploadSchoolCalendar(file, schoolChild, familyId));
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setProgress(null);
      if (schoolRef.current) schoolRef.current.value = "";
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          📷 Add From Photos
        </h2>
      </header>

      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        Snap a flyer, a practice schedule, a screenshot — or select a whole
        batch at once. Exhale reads each one and tracks what it finds. Anything
        it isn't sure about waits for your confirmation instead of being
        guessed.
      </p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
      >
        {busy
          ? progress.total === 1
            ? "Reading the image…"
            : `Reading photo ${Math.min(progress.done + 1, progress.total)} of ${progress.total}…`
          : "Choose photos"}
      </button>

      {result && (
        <div className="mt-3 space-y-1 font-micro text-xs text-sanctuary-navy/60">
          <p>
            {result.items.length === 0
              ? "Nothing trackable found."
              : `Found ${result.items.length} item${result.items.length === 1 ? "" : "s"}: ` +
                result.items
                  .map((i) => `${i.extracted_event} (${i.status === "COMMITTED" ? "added" : "awaiting your review"})`)
                  .join(" · ")}
          </p>
          {result.failures.map((f) => (
            <p key={f.name} className="text-looming-amber">
              {f.name} couldn't be read — {f.message}
            </p>
          ))}

          {/* Who's this for? — asked, never guessed. */}
          {result.unattributed.length > 0 && result.children.length > 0 && (
            <div className="!mt-3 rounded-2xl bg-pure-breath p-3">
              <p className="text-sanctuary-navy/75">
                {result.unattributed.length} item
                {result.unattributed.length === 1 ? " doesn't" : "s don't"} say
                who they're for. Who is this schedule for?
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {result.children.map((name) => (
                  <button
                    key={name}
                    onClick={() => attributeAll(name)}
                    disabled={attributing}
                    className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
                  >
                    {attributing ? "…" : name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {result.attributedTo && (
            <p className="text-sage-release">Filed under {result.attributedTo}.</p>
          )}
        </div>
      )}

      {/* --- the school-year calendar, which is care knowledge, not events --- */}
      {knownChildren.length > 0 && (
        <div className="mt-5 border-t border-sanctuary-navy/10 pt-4">
          <p className="font-micro text-sm font-medium text-sanctuary-navy/80">
            Is it a school-year calendar?
          </p>
          <p className="mt-1 font-micro text-xs leading-relaxed text-sanctuary-navy/55">
            Send it here instead. Exhale reads the whole year — first day, last
            day, teacher workshops, breaks — and files it as that child's school
            calendar. Then a random day off stops being a mystery: Exhale knows
            school isn't covering them, so it's on you.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              value={schoolChild}
              onChange={(e) => setSchoolChild(e.target.value)}
              className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sm text-sanctuary-navy focus:border-sage-release focus:outline-none"
            >
              {knownChildren.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <input
              ref={schoolRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => handleSchool(e.target.files?.[0])}
            />
            <button
              onClick={() => schoolRef.current?.click()}
              disabled={busy}
              className="rounded-full border border-sanctuary-navy/15 px-4 py-2 font-micro text-sm text-sanctuary-navy transition hover:bg-pure-breath disabled:opacity-50"
            >
              Upload school calendar
            </button>
          </div>
          {schoolResult && (
            <p className="mt-2 font-micro text-xs text-sage-release">
              {schoolChild}'s school year is set —{" "}
              {schoolResult.no_school_days ?? schoolResult.synced_no_school_days ?? 0}{" "}
              no-school days are now days Exhale knows are yours to cover.
            </p>
          )}
        </div>
      )}

      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
