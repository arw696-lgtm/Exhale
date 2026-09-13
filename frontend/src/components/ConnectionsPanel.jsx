import React, { useEffect, useState } from "react";
import {
  fetchConnections,
  fetchFeedUrl,
  fetchNotifications,
  saveNotifications,
  sendTestNotification,
  startConnect,
  syncGmailNow,
} from "../data/api.js";

/**
 * Connections panel — the "Connect Google / Connect Outlook" buttons and status,
 * plus the outbound channel: where 🔴 critical alerts get emailed (each exactly
 * once — the briefing stays the live picture).
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
  const [notify, setNotify] = useState(null); // prefs from the API
  const [notifyEmail, setNotifyEmail] = useState("");
  const [notifyStatus, setNotifyStatus] = useState(null); // transient feedback
  const [scanning, setScanning] = useState(false);
  const [scanReport, setScanReport] = useState(null);
  const [scanError, setScanError] = useState(null);

  const runScan = async () => {
    setScanning(true);
    setScanError(null);
    setScanReport(null);
    try {
      setScanReport(await syncGmailNow([], familyId));
    } catch (e) {
      // A first scan reads six months and can outlast the connection — a
      // locked phone is enough. The server keeps going, so a dropped
      // connection is not a failed scan and must not be reported as one.
      const dropped = /fetch|network|load failed|timeout/i.test(e.message ?? "");
      setScanError(
        dropped
          ? "Lost the connection while reading — the scan usually keeps going " +
            "on the server. Give it a few minutes, then check Today."
          : e.message
      );
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    let alive = true;
    fetchConnections(familyId).then((c) => alive && setConns(c));
    fetchFeedUrl(familyId).then((u) => alive && setFeedUrl(u));
    fetchNotifications(familyId).then((n) => {
      if (!alive) return;
      setNotify(n);
      setNotifyEmail(n?.email ?? "");
    });
    return () => {
      alive = false;
    };
  }, [familyId]);

  const saveAlerts = async () => {
    setNotifyStatus(null);
    try {
      const saved = await saveNotifications(notifyEmail.trim() || null, familyId);
      setNotify(saved);
      setNotifyEmail(saved.email ?? "");
      setNotifyStatus(saved.email ? "Saved ✓" : "Alerts off");
    } catch (e) {
      setNotifyStatus(e.message);
    }
  };

  const testAlerts = async () => {
    setNotifyStatus(null);
    try {
      const { sent_to } = await sendTestNotification(familyId);
      setNotifyStatus(`Test sent to ${sent_to} ✓`);
    } catch (e) {
      setNotifyStatus(e.message);
    }
  };

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
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
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
                <p className="mt-0.5 text-sanctuary-navy/70">
                  {status.connected
                    ? `Connected${
                        (status.accounts ?? 1) > 1 ? ` · ${status.accounts} accounts` : ""
                      }${
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

      {/* Exhale reads the inbox on its own schedule, but "read it now" had no
          button anywhere — so after connecting an account, or changing
          anything about how mail is read, there was nothing to press and no
          way to tell whether it had worked. */}
      {conns.google?.connected && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="font-micro text-sm text-sanctuary-navy/70">
              Exhale checks for new mail on its own. You can also read it now.
            </p>
            <button
              onClick={runScan}
              disabled={scanning}
              className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
            >
              {scanning ? "Reading…" : "Scan my email now"}
            </button>
          </div>
          {scanReport && (
            <p className="mt-2 font-micro text-sm text-sanctuary-navy/70">
              Read {scanReport.scanned} message
              {scanReport.scanned === 1 ? "" : "s"}: {scanReport.committed}{" "}
              tracked, {scanReport.pending} waiting for you, {scanReport.rejected}{" "}
              left alone.
            </p>
          )}
          {scanError && (
            <p className="mt-2 font-micro text-sm text-amber-text">{scanError}</p>
          )}
        </div>
      )}

      {feedUrl && (
        <div className="mt-4 flex items-start justify-between gap-3 border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/70">
          <span>
            <span className="font-semibold text-sanctuary-navy/80">Family calendar feed</span>
            {" — what's protected, what's due, and where cover is needed. Subscribe on a phone, or paste it into a family display (Skylight: Sync new calendar → Calendar URL)."}
            <span className="mt-1 block text-sanctuary-navy/70">
              Anyone with this link can read the feed — share it like a password.
            </span>
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

      {notify && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/70">
          <p className="font-semibold text-sanctuary-navy/80">🔴 Critical alerts by email</p>
          <p className="mt-0.5">
            When something urgent surfaces, Exhale emails you — each alert exactly
            once. Leave blank to keep alerts off.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="email"
              value={notifyEmail}
              placeholder="you@example.com"
              onChange={(e) => setNotifyEmail(e.target.value)}
              className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-1 text-sanctuary-navy outline-none focus:border-sage-release"
            />
            <button
              onClick={saveAlerts}
              className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-medium text-sanctuary-navy transition hover:bg-sage-release/20"
            >
              Save
            </button>
            {notify.email && notify.smtp_configured && (
              <button
                onClick={testAlerts}
                className="rounded-full border border-sanctuary-navy/15 px-3 py-1 font-medium text-sanctuary-navy/70 transition hover:bg-sanctuary-navy/5"
              >
                Send test
              </button>
            )}
            {notifyStatus && <span className="text-sanctuary-navy/70">{notifyStatus}</span>}
          </div>
          {notify.email && !notify.smtp_configured && (
            <p className="mt-1.5 text-amber-text">
              Address saved, but this server has no outgoing email configured yet
              (EXHALE_SMTP_HOST) — alerts will start once it does.
            </p>
          )}
        </div>
      )}

      <p className="mt-4 border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/70">
        No account setup on your end — one click, the provider's own sign-in. Or
        paste a published calendar link / upload a `.ics` file.
      </p>

      {error && (
        <p className="mt-3 font-micro text-xs text-amber-text">
          {error.includes("not configured")
            ? "That sign-in isn't set up on this server yet."
            : error}
        </p>
      )}
    </section>
  );
}
