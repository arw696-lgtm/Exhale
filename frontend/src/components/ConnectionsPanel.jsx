import React, { useEffect, useState } from "react";
import { fetchConnections, startGoogleConnect } from "../data/api.js";

/**
 * Connections panel — the "Connect Google" button and link status.
 *
 * The visible face of the OAuth flow: one click sends the user to Google's own
 * consent screen; on return their calendar + inbox feed the engines. Renders
 * nothing when connection status isn't available (offline/anonymous).
 */
export default function ConnectionsPanel({ familyId }) {
  const [conns, setConns] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchConnections(familyId).then((c) => alive && setConns(c));
    return () => {
      alive = false;
    };
  }, [familyId]);

  if (conns === null) return null; // status unavailable (offline demo / anon)

  const google = conns.google ?? { connected: false };

  const onConnect = async () => {
    setError(null);
    setBusy(true);
    try {
      await startGoogleConnect(familyId); // redirects to Google on success
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-4">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🔗 Connections
        </h2>
      </header>

      <div className="flex items-center justify-between font-micro text-sm">
        <div>
          <p className="font-semibold text-sanctuary-navy">Google — Calendar &amp; Gmail</p>
          <p className="mt-0.5 text-sanctuary-navy/60">
            {google.connected
              ? `Connected${
                  google.connected_at
                    ? " · " + new Date(google.connected_at).toLocaleDateString()
                    : ""
                }`
              : "Read-only. Powers your availability and inbox obligations."}
          </p>
        </div>
        {google.connected ? (
          <span className="rounded-full bg-sage-release/15 px-3 py-1 font-semibold text-sanctuary-navy/70">
            ✓ Connected
          </span>
        ) : (
          <button
            onClick={onConnect}
            disabled={busy}
            className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
          >
            {busy ? "Opening…" : "Connect Google"}
          </button>
        )}
      </div>

      {error && (
        <p className="mt-3 font-micro text-xs text-looming-amber">
          {error.includes("not configured")
            ? "Google sign-in isn't set up on this server yet."
            : error}
        </p>
      )}
    </section>
  );
}
