import React, { useState } from "react";
import { login, signup } from "../data/api.js";

/**
 * Login / signup screen (Part 3 auth, §8 brand system).
 *
 * Signup either founds a new household or joins an existing one via its
 * invite code (the caregiver invite loop, §13.2).
 */
export default function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", displayName: "", inviteCode: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = mode === "login" ? await login(form) : await signup(form);
      onAuthed(session.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const field =
    "w-full rounded-xl border border-sanctuary-navy/15 bg-white px-4 py-2.5 " +
    "font-micro text-sm text-sanctuary-navy placeholder:text-sanctuary-navy/35 " +
    "focus:border-sage-release focus:outline-none";

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <header className="mb-8 text-center">
          <h1 className="font-display text-5xl italic text-sanctuary-navy">Exhale</h1>
          <p className="mt-2 font-micro text-sm text-sanctuary-navy/60">
            You aren't disorganized. You're just carrying too much data.
            <br />
            Let us remember it for you.
          </p>
        </header>

        <div className="rounded-card bg-white p-6 shadow-card">
          {/* Mode toggle */}
          <div className="mb-5 grid grid-cols-2 rounded-full bg-pure-breath p-1">
            {["login", "signup"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setError(null); }}
                className={
                  "rounded-full py-1.5 font-micro text-sm font-semibold transition " +
                  (mode === m
                    ? "bg-sanctuary-navy text-white"
                    : "text-sanctuary-navy/60 hover:text-sanctuary-navy")
                }
              >
                {m === "login" ? "Log in" : "Create account"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "signup" && (
              <input
                className={field}
                placeholder="Your first name"
                value={form.displayName}
                onChange={set("displayName")}
                required
              />
            )}
            <input
              className={field}
              type="email"
              placeholder="Email"
              value={form.email}
              onChange={set("email")}
              required
            />
            <input
              className={field}
              type="password"
              placeholder={mode === "signup" ? "Password (8+ characters)" : "Password"}
              value={form.password}
              onChange={set("password")}
              minLength={mode === "signup" ? 8 : undefined}
              required
            />
            {mode === "signup" && (
              <input
                className={field}
                placeholder="Family invite code (optional)"
                value={form.inviteCode}
                onChange={set("inviteCode")}
              />
            )}

            {error && (
              <p className="rounded-xl border-l-4 border-looming-amber bg-looming-amber/10 px-3 py-2 font-micro text-sm text-sanctuary-navy">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-full bg-sanctuary-navy py-2.5 font-micro text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "One moment…" : mode === "login" ? "Log in →" : "Start breathing easier →"}
            </button>
          </form>

          {mode === "signup" && (
            <p className="mt-4 text-center font-micro text-xs text-sanctuary-navy/50">
              Have a partner's invite code? Enter it to join their household.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
