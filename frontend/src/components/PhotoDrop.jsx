import React, { useRef, useState } from "react";
import { uploadPhoto } from "../data/api.js";

/**
 * Photo Drop — "just screenshot it and add it in."
 *
 * Sends a flyer photo / calendar screenshot through vision extraction; every
 * item it reads flows through the same routing + credibility rules as email,
 * so uncertain reads land in the Review Queue rather than silently committing.
 */
export default function PhotoDrop({ familyId, knownChildren = [], onChanged }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFile = async (file) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = await uploadPhoto(file, familyId, knownChildren);
      setResult(body);
      onChanged?.();
    } catch (e) {
      setError(
        e.message.includes("not configured")
          ? "Photo reading isn't set up on this server yet (needs an Anthropic key)."
          : e.message
      );
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          📷 Add From a Photo
        </h2>
      </header>

      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        Snap a flyer, a school calendar, or a screenshot — Exhale reads it and
        tracks what it finds. Anything it isn't sure about waits for your
        confirmation instead of being guessed.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
      >
        {busy ? "Reading the image…" : "Choose a photo"}
      </button>

      {result && (
        <p className="mt-3 font-micro text-xs text-sanctuary-navy/60">
          {result.extracted === 0
            ? "Nothing trackable found in that image."
            : `Found ${result.extracted} item${result.extracted === 1 ? "" : "s"}: ` +
              result.items
                .map((i) => `${i.extracted_event} (${i.status === "COMMITTED" ? "added" : "awaiting your review"})`)
                .join(" · ")}
        </p>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
