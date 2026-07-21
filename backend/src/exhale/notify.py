"""Critical-alert notifications — the brain reaches out (closing the pull-only gap).

Until now every insight waited for someone to open the app: a 🔴 care gap 30
hours out could pass unseen. This module gives Exhale an outbound channel —
email first, because every household has it and the transport is dependency-
free (stdlib ``smtplib``).

Discipline:

* **Alert once.** Every alert has a stable key; sent keys persist in the
  encrypted profile, so a critical item nags exactly once, not every cycle.
* **Digest, not spray.** All of a family's new critical items go in one email
  per cycle.
* **Same honesty as the briefing.** Alert lines carry the *why* (the gap's
  reason / the obligation's source), never just a bare demand.
* **Config-gated.** No SMTP config → notifications are off; a family opts in
  by setting a notify address. Nothing surprises anyone.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage

from exhale.briefing import build_weekly_briefing
from exhale.coverage import build_care_watch
from exhale.forgetting_engine import ThreatLevel

log = logging.getLogger("exhale.notify")


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    sender: str
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "SmtpConfig | None":
        host = os.environ.get("EXHALE_SMTP_HOST")
        sender = os.environ.get("EXHALE_SMTP_FROM")
        if not host or not sender:
            return None
        return cls(
            host=host,
            port=int(os.environ.get("EXHALE_SMTP_PORT", "587")),
            username=os.environ.get("EXHALE_SMTP_USER"),
            password=os.environ.get("EXHALE_SMTP_PASSWORD"),
            sender=sender,
            use_tls=os.environ.get("EXHALE_SMTP_TLS", "1").strip().lower()
            in ("1", "true", "yes"),
        )


class EmailNotifier:
    """Sends alert digests over SMTP. ``smtp_factory`` is injectable for tests."""

    def __init__(self, config: SmtpConfig, *, smtp_factory=None) -> None:
        self.config = config
        self._smtp_factory = smtp_factory or (
            lambda: smtplib.SMTP(config.host, config.port, timeout=30)
        )

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.config.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with self._smtp_factory() as smtp:
            if self.config.use_tls:
                smtp.starttls()
            if self.config.username and self.config.password:
                smtp.login(self.config.username, self.config.password)
            smtp.send_message(msg)


def notifier_from_env(**kwargs) -> EmailNotifier | None:
    config = SmtpConfig.from_env()
    return EmailNotifier(config, **kwargs) if config else None


# --- alert discovery ----------------------------------------------------------------
def find_critical_alerts(store, family_id: str, *, now: datetime | None = None) -> list[dict]:
    """Every currently-🔴 item for a family, each with a stable dedupe key."""

    from exhale.coverage_config import CoverageModelIn, build_engine

    now = now or datetime.now()
    alerts: list[dict] = []

    # The forgetting engine subtracts an aware deadline from ``now`` — a naive
    # ``now`` must pick up the local zone first or the math raises.
    briefing = build_weekly_briefing(
        store.graph(family_id), now=now if now.tzinfo else now.astimezone()
    )
    for item in briefing["critical_threats"]:
        line = f"🔴 {item['title']}"
        if item.get("person"):
            line += f" — {item['person']}"
        line += f" · deadline {item['deadline']}"
        why = item.get("why") or {}
        if why.get("source_document_name"):
            line += f" · from “{why['source_document_name']}”"
        alerts.append({"key": f"obligation:{item['obligation_id']}", "line": line})

    model_cfg = store.profile(family_id).get("coverage_model")
    if model_cfg:
        engine = build_engine(CoverageModelIn(**model_cfg), now=now.replace(tzinfo=None))
        watch = build_care_watch(engine, now.date(), (now + timedelta(days=3)).date())
        for gap in watch["gaps"]:
            if gap["threat_level"] != ThreatLevel.CRITICAL.value:
                continue
            alerts.append({
                "key": f"caregap:{gap['start']}:{gap['end']}",
                "line": (
                    f"🔴 {watch['recipient']} uncovered {gap['date']} "
                    f"{gap['start'][11:16]}–{gap['end'][11:16]} — {gap['reason']}. "
                    f"{gap['suggested_action']}."
                ),
            })
    return alerts


def run_notification_cycle(store, notifier: EmailNotifier, *, now: datetime | None = None) -> dict:
    """One pass over all families: email each its *new* critical alerts.

    Sent alert keys persist in the profile so nothing is re-sent; one digest
    per family per cycle; per-family failures isolated like auto-sync.
    """

    report: dict = {"notified": {}, "skipped": {}, "errors": {}}
    for family_id in store.family_ids():
        try:
            profile = store.profile(family_id)
            to = profile.get("notify_email")
            if not to:
                report["skipped"][family_id] = "no notify_email set"
                continue
            already = set(profile.get("notified_alerts") or [])
            alerts = [a for a in find_critical_alerts(store, family_id, now=now)
                      if a["key"] not in already]
            if not alerts:
                report["skipped"][family_id] = "nothing new"
                continue

            lines = "\n".join(a["line"] for a in alerts)
            notifier.send(
                to,
                subject=f"Exhale: {len(alerts)} critical item"
                        f"{'s' if len(alerts) != 1 else ''} need attention",
                body=(
                    f"{lines}\n\n"
                    "Open your Exhale briefing to act on these.\n"
                    "— Exhale (you get each alert once; the briefing always has "
                    "the live picture)"
                ),
            )
            store.set_profile(
                family_id,
                notified_alerts=sorted(already | {a["key"] for a in alerts}),
            )
            report["notified"][family_id] = len(alerts)
        except Exception as exc:  # noqa: BLE001 — one family never stalls another
            log.warning("notify %s failed: %s", family_id, exc)
            report["errors"][family_id] = str(exc)
    return report
