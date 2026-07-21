import React, { useState } from "react";
import { saveCoverageModel } from "../data/api.js";

/**
 * Household Setup — the onboarding form for the coverage model.
 *
 * Turns "PUT a JSON document" into a form a primary caregiver can fill in two
 * minutes: the child who needs looking after, the caregivers (whoever they are
 * — parent, grandparent, guardian; with an optional work pattern on whichever
 * days they actually work, because nurses, retail, and shift workers aren't
 * Mon–Fri), and optionally the school year. Shown when the household has no
 * coverage model yet; once saved, Care Watch and work windows light up.
 */
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// The household runner isn't always "parent" (FAMILY_STRUCTURES §3.4). RELATIVE
// is the one role the engine treats specially: asked before suggesting a sitter.
const ROLES = [
  { value: "PARENT", label: "Parent" },
  { value: "GUARDIAN", label: "Guardian / foster" },
  { value: "RELATIVE", label: "Grandparent / relative / friend" },
  { value: "SITTER", label: "Sitter / nanny" },
];
const EMPTY_CG = {
  name: "",
  role: "PARENT",
  works: false,
  days: [0, 1, 2, 3, 4], // default Mon–Fri; any combination is valid
  start: "07:30",
  end: "16:30",
};

export default function SetupPanel({ familyId, onSaved }) {
  const [children, setChildren] = useState([""]);
  const [caregivers, setCaregivers] = useState([{ ...EMPTY_CG }, { ...EMPTY_CG }]);
  const [school, setSchool] = useState({ name: "", first: "", last: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const setCg = (i, patch) =>
    setCaregivers((cgs) => cgs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const setChildName = (i, name) =>
    setChildren((cs) => cs.map((c, j) => (j === i ? name : c)));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    const kids = children.map((c) => c.trim()).filter(Boolean);
    const named = caregivers.filter((c) => c.name.trim());
    if (kids.length === 0 || named.length === 0) {
      setError("Name at least one child and one caregiver.");
      return;
    }
    if (named.some((c) => c.works && c.days.length === 0)) {
      setError("Pick at least one workday for each caregiver who works a schedule.");
      return;
    }
    const schoolIn =
      school.name.trim() && school.first && school.last
        ? { name: school.name.trim(), first_day: school.first, last_day: school.last }
        : null;
    const model = {
      children: kids.map((name) => ({ recipient: { name }, school: schoolIn })),
      caregivers: named.map((c) => ({
        name: c.name.trim(),
        role: c.role,
        work_pattern: c.works
          ? { weekdays: [...c.days].sort((a, b) => a - b),
              start: `${c.start}:00`, end: `${c.end}:00`, basis: "INFERRED" }
          : null,
        events: [],
      })),
    };
    setBusy(true);
    try {
      await saveCoverageModel(model, familyId);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-1.5 " +
    "font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release";

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🏠 Set Up Your Household
        </h2>
      </header>
      <p className="mb-4 font-micro text-sm text-sanctuary-navy/60">
        Tell Exhale who needs looking after and who's around. Two minutes — then
        care gaps and work windows start computing themselves.
      </p>

      <form onSubmit={submit} className="space-y-4 font-micro text-sm">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase text-sanctuary-navy/50">
            Children who need supervision
          </label>
          <div className="space-y-2">
            {children.map((name, i) => (
              <div key={i} className="flex items-center gap-2">
                <input className={input} value={name}
                       placeholder={i === 0 ? "e.g. Stevie" : "Another child"}
                       onChange={(e) => setChildName(i, e.target.value)} />
                {children.length > 1 && (
                  <button type="button" aria-label={`Remove child ${i + 1}`}
                          onClick={() => setChildren((cs) => cs.filter((_, j) => j !== i))}
                          className="text-sanctuary-navy/40 hover:text-looming-amber">
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          <button type="button" onClick={() => setChildren((cs) => [...cs, ""])}
                  className="mt-2 text-xs font-medium text-sanctuary-navy/60 underline-offset-2 hover:underline">
            + Add another child
          </button>
        </div>

        {caregivers.map((cg, i) => (
          <div key={i} className="rounded-xl border border-sanctuary-navy/10 p-3">
            <label className="mb-1 block text-xs font-semibold uppercase text-sanctuary-navy/50">
              Caregiver {i + 1}{i > 0 ? " (optional)" : ""}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <input className={input + " min-w-40 flex-1"} value={cg.name} placeholder="Name"
                     onChange={(e) => setCg(i, { name: e.target.value })} />
              <select
                value={cg.role}
                onChange={(e) => setCg(i, { role: e.target.value })}
                aria-label={`Role of caregiver ${i + 1}`}
                className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-1.5 font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <label className="mt-2 flex items-center gap-2 text-sanctuary-navy/70">
              <input type="checkbox" checked={cg.works}
                     onChange={(e) => setCg(i, { works: e.target.checked })} />
              Works a regular schedule
            </label>
            {cg.works && (
              <>
                <div className="mt-2 flex flex-wrap gap-1.5" role="group"
                     aria-label={`Workdays for caregiver ${i + 1}`}>
                  {DAY_LABELS.map((label, day) => {
                    const on = cg.days.includes(day);
                    return (
                      <button key={day} type="button" aria-pressed={on}
                        onClick={() =>
                          setCg(i, {
                            days: on
                              ? cg.days.filter((d) => d !== day)
                              : [...cg.days, day],
                          })
                        }
                        className={
                          "rounded-full border px-2.5 py-1 text-xs font-medium transition " +
                          (on
                            ? "border-sage-release/60 bg-sage-release/20 text-sanctuary-navy"
                            : "border-sanctuary-navy/15 text-sanctuary-navy/50 hover:bg-sanctuary-navy/5")
                        }>
                        {label}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-2 flex items-center gap-2 text-sanctuary-navy/70">
                  <input type="time" value={cg.start} className={input}
                         onChange={(e) => setCg(i, { start: e.target.value })} />
                  <span>to</span>
                  <input type="time" value={cg.end} className={input}
                         onChange={(e) => setCg(i, { end: e.target.value })} />
                </div>
                <p className="mt-1.5 text-xs text-sanctuary-navy/50">
                  Tap the days they work — shift and weekend schedules welcome. Same
                  hours each workday; sync their calendar for anything irregular.
                </p>
              </>
            )}
          </div>
        ))}

        <div className="rounded-xl border border-sanctuary-navy/10 p-3">
          <label className="mb-1 block text-xs font-semibold uppercase text-sanctuary-navy/50">
            School year (optional — or snap the calendar later)
          </label>
          <p className="mb-2 text-xs text-sanctuary-navy/50">
            Applies to every child above. Different schools or a non-school-age
            kid? Save now, then snap each school's calendar photo to set them
            per child.
          </p>
          <input className={input} value={school.name} placeholder="School name"
                 onChange={(e) => setSchool({ ...school, name: e.target.value })} />
          <div className="mt-2 flex items-center gap-2 text-sanctuary-navy/70">
            <input type="date" value={school.first} className={input}
                   onChange={(e) => setSchool({ ...school, first: e.target.value })} />
            <span>to</span>
            <input type="date" value={school.last} className={input}
                   onChange={(e) => setSchool({ ...school, last: e.target.value })} />
          </div>
        </div>

        <button type="submit" disabled={busy}
                className="rounded-full border border-sage-release/40 bg-sage-release/10 px-5 py-2 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50">
          {busy ? "Saving…" : "Save household"}
        </button>
        {error && <p className="text-xs text-looming-amber">{error}</p>}
      </form>
    </section>
  );
}
