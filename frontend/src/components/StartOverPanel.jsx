import React, { useState } from "react";
import { resetHousehold, syncGmailNow } from "../data/api.js";

/**
 * Start over — throw away everything Exhale read out of the mail.
 *
 * The case this exists for: a scan that ran before the filters that would
 * have caught its junk. Re-scanning alone can't fix that, because the scan
 * skips every message it has already seen — so the old extractions simply
 * stay. Clearing them is the only way to get a better reader applied to mail
 * already read.
 *
 * The household itself survives: people, coverage, connected accounts, away
 * periods, typed tasks, notification settings. Only what was derived from
 * email goes, and it comes back on the next scan.
 *
 * Deliberately awkward. It is two steps behind a closed door and needs the
 * word typed out, because it cannot be undone and nobody should reach it by
 * tapping through. The confirmation phrase is a word, not a checkbox: reading
 * and typing it is the point.
 */
const PHRASE = "start over";

export default function StartOverPanel({ familyId, onDone }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [scanned, setScanned] = useState(null);

  // Clearing without rebuilding leaves an empty app, so the scan is offered
  // right here rather than described and left somewhere else to find.
  const scan = async () => {
    setScanning(true);
    setError(null);
    try {
      setScanned(await syncGmailNow([], familyId));
      onDone?.();
    } catch (e) {
      // Reading six months of mail can outlast the connection — a phone
      // locking the screen is enough. The server does not stop when the
      // browser gives up, so a dropped connection must not be reported as a
      // failed scan. A real API error (Gmail not connected, say) arrives as a
      // message from the server and is shown as-is.
      const dropped = /fetch|network|load failed|timeout/i.test(e.message ?? "");
      setError(
        dropped
          ? "Lost the connection while reading — the scan usually keeps going " +
            "on the server. Give it a few minutes, then check Today."
          : e.message
      );
    } finally {
      setScanning(false);
    }
  };

  const armed = typed.trim().toLowerCase() === PHRASE;

  const run = async () => {
    if (!armed) return;
    setBusy(true);
    setError(null);
    try {
      const data = await resetHousehold(familyId);
      setResult(data.removed ?? {});
      setTyped("");
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
      <h2 className="font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/70">
        Start over
      </h2>

      {result ? (
        <div className="mt-2 font-micro text-sm text-sanctuary-navy/70">
          <p>
            Cleared {result.ledger_entries} item
            {result.ledger_entries === 1 ? "" : "s"} and{" "}
            {result.graph_nodes} record{result.graph_nodes === 1 ? "" : "s"}.
            Your household, connections and settings are untouched.
          </p>

          {scanned ? (
            <p className="mt-3 text-sanctuary-navy">
              Read {scanned.scanned} message
              {scanned.scanned === 1 ? "" : "s"}: {scanned.committed} tracked,{" "}
              {scanned.pending} waiting for you to confirm, {scanned.rejected}{" "}
              left alone. Have a look at Today.
            </p>
          ) : (
            <>
              <p className="mt-3 text-sanctuary-navy">
                Now read your mail again with the current reader. This covers
                the last six months, so give it a few minutes.
              </p>
              <button
                onClick={scan}
                disabled={scanning}
                className="mt-3 rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-2 font-micro text-sm font-semibold text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
              >
                {scanning ? "Reading your mail…" : "Scan my email now"}
              </button>
            </>
          )}
        </div>
      ) : (
        <>
          <p className="mt-2 font-micro text-sm text-sanctuary-navy/70">
            Throws away everything Exhale read out of your email and lets the
            next scan start fresh. Useful when a scan ran before Exhale learned
            to filter something out — re-scanning on its own skips mail it has
            already seen, so the old items would stay.
          </p>
          <p className="mt-2 font-micro text-sm text-sanctuary-navy/70">
            Your people, coverage, connected accounts, away periods and typed
            tasks all stay. This cannot be undone.
          </p>

          {!open ? (
            <button
              onClick={() => setOpen(true)}
              className="mt-4 rounded-full border border-sanctuary-navy/15 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath"
            >
              Start over…
            </button>
          ) : (
            <div className="mt-4">
              <label
                htmlFor="start-over-confirm"
                className="block font-micro text-sm text-sanctuary-navy/70"
              >
                Type <span className="font-semibold text-sanctuary-navy">{PHRASE}</span> to
                confirm.
              </label>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  id="start-over-confirm"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoComplete="off"
                  className="min-w-0 flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sanctuary-navy placeholder:text-sanctuary-navy/70 focus:border-sage-release focus:outline-none"
                  placeholder={PHRASE}
                />
                <button
                  onClick={run}
                  disabled={!armed || busy}
                  className="rounded-full border border-amber-text/40 bg-looming-amber/10 px-4 py-2 font-micro text-sm font-semibold text-amber-text transition hover:bg-looming-amber/20 disabled:opacity-40"
                >
                  {busy ? "Clearing…" : "Clear everything"}
                </button>
                <button
                  onClick={() => {
                    setOpen(false);
                    setTyped("");
                  }}
                  disabled={busy}
                  className="font-micro text-sm text-sanctuary-navy/70 underline-offset-2 hover:underline"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {error && <p className="mt-3 font-micro text-sm text-amber-text">{error}</p>}
    </section>
  );
}
