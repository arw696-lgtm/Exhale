import React, { useRef, useState } from "react";
import { uploadPhoto } from "../data/api.js";

/**
 * Photo Drop — "just screenshot it and add it in."
 *
 * Takes one photo or a whole backpack-dump of them (the file picker allows
 * multi-select) and sends each through vision extraction. Files are read
 * sequentially with visible progress; one unreadable photo never sinks the
 * rest. Every item flows through the same routing + credibility rules as
 * email, so uncertain reads land in the Review Queue rather than silently
 * committing.
 */
export default function PhotoDrop({ familyId, knownChildren = [], onChanged }) {
  const inputRef = useRef(null);
  const [progress, setProgress] = useState(null); // {done, total} while busy
  const [result, setResult] = useState(null); // {items, failures}
  const [error, setError] = useState(null);

  const busy = progress !== null;

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList ?? []);
    if (files.length === 0) return;
    setError(null);
    setResult(null);
    setProgress({ done: 0, total: files.length });

    const items = [];
    const failures = [];
    let anyOk = false;
    for (const [index, file] of files.entries()) {
      setProgress({ done: index, total: files.length });
      try {
        const body = await uploadPhoto(file, familyId, knownChildren);
        anyOk = true;
        items.push(...(body.items ?? []));
      } catch (e) {
        if (e.message.includes("not configured")) {
          // Server-wide condition — no point trying the remaining files.
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

    setResult({ items, failures });
    setProgress(null);
    if (inputRef.current) inputRef.current.value = "";
    if (anyOk) onChanged?.();
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          📷 Add From Photos
        </h2>
      </header>

      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        Snap a flyer, a school calendar, a screenshot — or select a whole batch
        at once. Exhale reads each one and tracks what it finds. Anything it
        isn't sure about waits for your confirmation instead of being guessed.
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
        </div>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
