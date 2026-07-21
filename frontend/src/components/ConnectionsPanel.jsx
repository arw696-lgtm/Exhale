import React, { useEffect, useState } from "react";
import { fetchConnections, fetchFeedUrl, startConnect } from "../data/api.js";

/**
 * Connections panel — the "Connect Google / Connect Outlook" buttons and status.
 *
 * The visible face of the OAuth flows: one click sends the user to the
 * provider's own consent screen; on return their calendar + inbox feed the
 * engines. Renders nothing when status isn't available (offline / anonymous).
 */
const PROVIDERS = [
  { key: "google", label: "Google — Calendar & Gmail" },
  { key: "microsoft", label: "Outlook — Calendar & Mail" },
];

export default function ConnectionsPanel({ familyId }) {
  const [conns, setConns] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [feedUrl, setFeedUrl] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchConnections(familyId).then((c) => alive && setConns(c));
    fetchFeedUrl(familyId).then((u) => alive && setFeedUrl(u));
    return () => {
      alive = false;
    };
  }, [familyId]);

  if (conns === null) return null; // status unavailable (offline demo / anon)

  const onConnect = async (provider) => {
    setError(null);
    setBusy(provider);
    try {
      await startConnect(provider, familyId); // redirects on success
    } catch (e) {
      setError(e.message);
      setBusy(null);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-4">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🔗 Connections
        </h2>
      </header>

      <ul className="space-y-4">
        {PROVIDERS.map(({ key, label }) => {
          const status = conns[key] ?? { connected: false };
          return (
            <li key={key} className="flex items-center justify-between font-micro text-sm">
              <div>
                <p className="font-semibold text-sanctuary-navy">{label}</p>
                <p className="mt-0.5 text-sanctuary-navy/60">
                  {status.connected
                    ? `Connected${
                        status.connected_at
                          ? " · " + new Date(status.connected_at).toLocaleDateString()
                          : ""
                      }`
                    : "Read-only. Powers availability and inbox obligations."}
                </p>
              </div>
              {status.connected ? (
                <span className="rounded-full bg-sage-release/15 px-3 py-1 font-semibold text-sanctuary-navy/70">
                  ✓ Connected
                </span>
              ) : (
                <button
                  onClick={() => onConnect(key)}
                  disabled={busy === key}
                  className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
                >
                  {busy === key ? "Opening…" : `Connect ${key === "google" ? "Google" : "Outlook"}`}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {feedUrl && (
        <div className="mt-4 flex items-center justify-between border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/60">
          <span>
            <span className="font-semibold text-sanctuary-navy/80">Exhale calendar feed</span>
            {" — subscribe on your phone and Exhale's events show up in your calendar (and CarPlay)."}
          </span>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(feedUrl);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-medium text-sanctuary-navy transition hover:bg-sage-release/20"
          >
            {copied ? "Copied ✓" : "Copy link"}
          </button>
        </div>
      )}

      <p className="mt-4 border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/40">
        No account setup on your end — one click, the provider's own sign-in. Or
        paste a published calendar link / upload a `.ics` file.
      </p>

      {error && (
        <p className="mt-3 font-micro text-xs text-looming-amber">
          {error.includes("not configured")
            ? "That sign-in isn't set up on this server yet."
            : error}
        </p>
      )}
    </section>
  );
}
