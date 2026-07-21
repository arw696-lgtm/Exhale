"""Tests for the outbound critical-alert channel (notify.py)."""

from datetime import datetime, time, timedelta

from exhale.auto_sync import run_cycle
from exhale.notify import (
    EmailNotifier,
    SmtpConfig,
    find_critical_alerts,
    notifier_from_env,
    run_notification_cycle,
)
from exhale.seed import DEMO_FAMILY_ID, seed_demo
from exhale.store import HouseholdStore


class FakeSMTP:
    """Stands in for smtplib.SMTP: records the protocol dance and the message."""

    def __init__(self, log: list) -> None:
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.log.append(("starttls",))

    def login(self, user, password):
        self.log.append(("login", user))

    def send_message(self, msg):
        self.log.append(("send", msg))


def _notifier(log: list) -> EmailNotifier:
    cfg = SmtpConfig(host="smtp.test", port=587, username="mailer",
                     password="hunter2", sender="alerts@exhale.test")
    return EmailNotifier(cfg, smtp_factory=lambda: FakeSMTP(log))


def _sent_messages(log: list) -> list:
    return [entry[1] for entry in log if entry[0] == "send"]


def _seeded_store() -> HouseholdStore:
    store = HouseholdStore()
    seed_demo(store)  # demo family carries imminent high-impact obligations
    return store


# --- config ------------------------------------------------------------------------
def test_smtp_config_absent_means_notifications_off(monkeypatch):
    for var in ("EXHALE_SMTP_HOST", "EXHALE_SMTP_FROM"):
        monkeypatch.delenv(var, raising=False)
    assert SmtpConfig.from_env() is None
    assert notifier_from_env() is None


def test_smtp_config_from_env(monkeypatch):
    monkeypatch.setenv("EXHALE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EXHALE_SMTP_FROM", "exhale@example.com")
    monkeypatch.setenv("EXHALE_SMTP_PORT", "2525")
    monkeypatch.setenv("EXHALE_SMTP_TLS", "0")
    cfg = SmtpConfig.from_env()
    assert cfg == SmtpConfig(host="smtp.example.com", port=2525, username=None,
                             password=None, sender="exhale@example.com", use_tls=False)


def test_email_notifier_speaks_smtp():
    log: list = []
    _notifier(log).send("andy@test", "subject", "body")
    assert ("starttls",) in log
    assert ("login", "mailer") in log
    (msg,) = _sent_messages(log)
    assert msg["To"] == "andy@test"
    assert msg["From"] == "alerts@exhale.test"


# --- alert discovery -----------------------------------------------------------
def test_find_critical_alerts_covers_seeded_obligations():
    store = _seeded_store()
    alerts = find_critical_alerts(store, DEMO_FAMILY_ID)
    assert alerts, "seeded demo family should have 🔴 items"
    assert all(a["key"].startswith("obligation:") for a in alerts)
    assert all(a["line"].startswith("🔴") for a in alerts)


def test_find_critical_alerts_includes_imminent_care_gaps():
    store = HouseholdStore()
    fam = "family_gap_alerts"
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    store.set_profile(fam, coverage_model={
        "recipient": {"name": "Stevie",
                      "supervised_start": time(8, 0).isoformat(),
                      "supervised_end": time(18, 0).isoformat()},
        "caregivers": [{
            "name": "Andy",
            "work_pattern": {"weekdays": [0, 1, 2, 3, 4, 5, 6],
                             "start": "08:00:00", "end": "18:00:00",
                             "basis": "OBSERVED"},
        }],
    })
    alerts = find_critical_alerts(store, fam)
    gap_alerts = [a for a in alerts if a["key"].startswith("caregap:")]
    assert gap_alerts, "an all-day-uncovered child within 36h must alert"
    assert any(tomorrow.isoformat() in a["key"] for a in gap_alerts)
    assert all("Stevie" in a["line"] for a in gap_alerts)


# --- the cycle -----------------------------------------------------------------
def test_cycle_sends_one_digest_then_never_repeats():
    store = _seeded_store()
    store.set_profile(DEMO_FAMILY_ID, notify_email="andy@test")
    log: list = []
    notifier = _notifier(log)

    first = run_notification_cycle(store, notifier)
    assert first["notified"][DEMO_FAMILY_ID] >= 1
    (msg,) = _sent_messages(log)  # one digest, not one email per alert
    assert msg["To"] == "andy@test"
    assert "🔴" in msg.get_content()

    second = run_notification_cycle(store, notifier)
    assert second["skipped"][DEMO_FAMILY_ID] == "nothing new"
    assert len(_sent_messages(log)) == 1  # alert-once held


def test_cycle_skips_families_without_notify_email():
    store = _seeded_store()
    log: list = []
    report = run_notification_cycle(store, _notifier(log))
    assert report["skipped"][DEMO_FAMILY_ID] == "no notify_email set"
    assert _sent_messages(log) == []


def test_cycle_isolates_send_failures():
    store = _seeded_store()
    store.set_profile(DEMO_FAMILY_ID, notify_email="andy@test")

    class Exploding(EmailNotifier):
        def send(self, *a, **kw):
            raise ConnectionError("smtp down")

    cfg = SmtpConfig(host="x", port=587, username=None, password=None, sender="x@x")
    report = run_notification_cycle(store, Exploding(cfg))
    assert "smtp down" in report["errors"][DEMO_FAMILY_ID]
    # Nothing marked as sent — next healthy cycle retries the same alerts.
    assert not store.profile(DEMO_FAMILY_ID).get("notified_alerts")


def test_auto_sync_cycle_runs_notifications_when_notifier_present():
    store = _seeded_store()
    store.set_profile(DEMO_FAMILY_ID, notify_email="andy@test")
    log: list = []
    report = run_cycle(store, extractor=None, notifier=_notifier(log))
    assert report["notifications"]["notified"][DEMO_FAMILY_ID] >= 1
    assert len(_sent_messages(log)) == 1

    no_notifier = run_cycle(store, extractor=None)
    assert "notifications" not in no_notifier
