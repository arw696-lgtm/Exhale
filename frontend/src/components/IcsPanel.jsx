import React, { useRef, useState } from "react";
import { syncIcsUrl, uploadIcsFile } from "../data/api.js";

/**
 * ICS import — the bridge for calendars with no clean API: a personal iPhone
 * calendar, a shared family iCloud calendar, an Outlook calendar someone
 * published. Exhale reads it as OBSERVED busy time, feeding the same
 * Care-Coverage Engine as a connected Google Calendar.
 *
 * Only useful once a coverage model exists (children + caregivers) — the
 * events need somewhere to land. Renders nothing until then.
 */
function webcalHint(url) {
  return url.trim().toLowerCase().startsWith("webcal://");
}

export default function IcsPanel({ familyId, hasCoverageModel, onChanged }) {
  const fileRef = useRef(null);
  const [url, setUrl] = useState("");
  const [attendees, setAttendees] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!hasCoverageModel) return null;

  const names = () =>
    attendees.split(",").map((s) => s.trim()).filter(Boolean);

  const afterSync = (body) => {
    setResult(body);
    onChanged?.();
  };

  const doUrlSync = async () => {
    const list = names();
    if (!url.trim() || list.length === 0) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      afterSync(await syncIcsUrl(url.trim(), list, familyId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const doFileUpload = async (file) => {
    const list = names();
    if (!file || list.length === 0) {
      setError("Add who this calendar is for before choosing a file.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const content = await file.text();
      afterSync(await uploadIcsFile(content, list, familyId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          📆 Bring In a Calendar
        </h2>
      </header>

      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        For calendars that don't have a "Connect" button — a personal iPhone
        calendar, a shared family iCloud calendar, anything published as a
        link. Exhale reads it as real, observed time, so coverage gaps built
        on it are high-confidence instead of guesses.
      </p>

      <details className="mb-4 rounded-2xl bg-pure-breath p-4">
        <summary className="cursor-pointer font-micro text-sm font-medium text-sanctuary-navy/85">
          Where do I get an iPhone/iCloud calendar link?
        </summary>
        <ol className="mt-2 list-decimal space-y-1 pl-5 font-micro text-xs leading-relaxed text-sanctuary-navy/65">
          <li>
            Open <span className="font-medium">icloud.com/calendar</span> in a
            browser (or the info button next to a calendar in the iPhone
            Calendar app).
          </li>
          <li>
            Find the calendar you want — a shared "Family" one, or your own —
            and turn on <span className="font-medium">Public Calendar</span>.
          </li>
          <li>
            Copy the link it gives you. It starts with{" "}
            <code className="rounded bg-sanctuary-navy/8 px-1">webcal://</code>
            — change just that part to{" "}
            <code className="rounded bg-sanctuary-navy/8 px-1">https://</code>{" "}
            and paste it below.
          </li>
        </ol>
        <p className="mt-2 font-micro text-xs text-sanctuary-navy/45">
          No hosting to set up? Export the calendar to a .ics file instead and
          upload it below — same result, no link required.
        </p>
      </details>

      <div className="space-y-2">
        <input
          value={attendees}
          onChange={(e) => setAttendees(e.target.value)}
          placeholder="Who is this calendar for? (e.g. Ali)"
          className="w-full rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sm text-sanctuary-navy placeholder:text-sanctuary-navy/35 focus:border-sage-release focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://p.../published.ics"
            className="min-w-0 flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sm text-sanctuary-navy placeholder:text-sanctuary-navy/35 focus:border-sage-release focus:outline-none"
          />
          <button
            onClick={doUrlSync}
            disabled={busy || !url.trim() || names().length === 0}
            className="shrink-0 rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
          >
            {busy ? "Reading…" : "Sync link"}
          </button>
        </div>
        {webcalHint(url) && (
          <p className="font-micro text-xs text-looming-amber">
            Change "webcal://" to "https://" at the start of the link.
          </p>
        )}

        <div className="flex items-center gap-2 pt-1">
          <span className="font-micro text-xs text-sanctuary-navy/45">or</span>
          <input
            ref={fileRef}
            type="file"
            accept=".ics,text/calendar"
            className="hidden"
            onChange={(e) => doFileUpload(e.target.files?.[0])}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-micro text-sm text-sanctuary-navy transition hover:bg-pure-breath disabled:opacity-50"
          >
            Upload a .ics file
          </button>
        </div>
      </div>

      {result && (
        <p className="mt-3 font-micro text-xs text-sanctuary-navy/60">
          Synced {result.synced_busy_events} event
          {result.synced_busy_events === 1 ? "" : "s"} for {result.holder}.
        </p>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
