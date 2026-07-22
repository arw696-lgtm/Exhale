"""Background auto-sync — the product re-pulls its sources by itself.

Every sync endpoint is on-demand; a real household brain refreshes without being
asked. This module replays, on a schedule, the syncs each family has already
performed once by hand: when a manual ``/sync/calendar``, ``/sync/outlook``, or
``/sync/ics`` succeeds, the API remembers its parameters in the family profile
(``sync_configs``, encrypted at rest like everything else); each cycle walks
every family and re-runs the remembered pulls. Gmail re-syncs whenever the
family has a connected Google account (its watermark already makes it
incremental).

Failure discipline: one family's broken feed must never stall the household
next door — every unit of work is individually caught and reported, and the
cycle report says exactly what ran and what failed. Enable by setting
``EXHALE_AUTO_SYNC_MINUTES`` (unset/0 = off, the default — tests and dev stay
deterministic).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from exhale.connections import accounts_for, first_account, watermark_key
from exhale.connectors.gcal import GoogleCalendarConnector
from exhale.connectors.gmail import GmailConnector
from exhale.connectors.ics import ICSCalendarConnector
from exhale.connectors.msgraph import GraphCalendarConnector
from exhale.coverage_config import CoverageModelIn, merge_events
from exhale.extraction import ExtractionContext
from exhale.oauth import config_from_env
from exhale.retro_scan import run_incremental_sync

log = logging.getLogger("exhale.auto_sync")


def _accounts(profile: dict, provider: str) -> dict[str, dict]:
    """Every member's usable grant for ``provider`` (legacy shape included)."""

    return accounts_for(profile.get("connections"), provider)


def _tokens(profile: dict, provider: str, account: str | None = None) -> dict | None:
    """One grant — the remembered ``account``'s if it still exists, else the
    first available (a revoked member's replay degrades, never breaks)."""

    accounts = _accounts(profile, provider)
    if account and account in accounts:
        return accounts[account]
    return first_account(profile.get("connections"), provider)


def _known_children(profile: dict) -> list[str]:
    model = profile.get("coverage_model") or {}
    names = [c["recipient"]["name"] for c in (model.get("children") or [])
             if c.get("recipient", {}).get("name")]
    if names:
        return names
    # Legacy single-child shape (profile stored before multi-child).
    if (model.get("recipient") or {}).get("name"):
        return [model["recipient"]["name"]]
    return []


def _sync_gmail(store, family_id: str, profile: dict, extractor) -> dict:
    """Pull EVERY connected member's inbox — two parents' Gmails both feed the
    family graph, each on its own watermark. Per-account failures isolated."""

    accounts = _accounts(profile, "google")
    if not accounts:
        return {"skipped": "google not connected"}
    cfg = config_from_env("google")
    ctx = ExtractionContext(known_children=_known_children(profile))
    report: dict = {}
    for user_key, tokens in sorted(accounts.items()):
        try:
            connector = GmailConnector(
                access_token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
                client_id=cfg.client_id if cfg else None,
                client_secret=cfg.client_secret if cfg else None,
            )
            result = run_incremental_sync(
                connector, store, family_id, ctx, extractor=extractor,
                watermark_key=watermark_key("google", user_key),
            )
            report[user_key] = {"scanned": result.scanned,
                                "committed": result.committed}
        except Exception as exc:  # noqa: BLE001 — one inbox never blocks the other
            log.warning("gmail auto-sync %s/%s failed: %s", family_id, user_key, exc)
            report[user_key] = {"error": str(exc)}
    return report


def _replay_calendar(store, family_id: str, profile: dict, config: dict) -> dict:
    tokens = _tokens(profile, "google", account=config.get("account"))
    model_cfg = profile.get("coverage_model")
    if tokens is None or not model_cfg:
        return {"skipped": "google not connected or no coverage model"}
    cfg = config_from_env("google")
    connector = GoogleCalendarConnector(
        caregiver_name=config["caregiver_name"],
        calendar_id=config.get("calendar_id", "primary"),
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        client_id=cfg.client_id if cfg else None,
        client_secret=cfg.client_secret if cfg else None,
    )
    now = datetime.now()
    events = connector.fetch_busy(now, now + timedelta(days=config.get("days", 120)))
    model = merge_events(CoverageModelIn(**model_cfg), config["caregiver_name"],
                         events, source_prefix="gcal_")
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {"synced_busy_events": len(events)}


def _replay_outlook(store, family_id: str, profile: dict, config: dict) -> dict:
    tokens = _tokens(profile, "microsoft", account=config.get("account"))
    model_cfg = profile.get("coverage_model")
    if tokens is None or not model_cfg:
        return {"skipped": "microsoft not connected or no coverage model"}
    cfg = config_from_env("microsoft")
    connector = GraphCalendarConnector(
        caregiver_name=config["caregiver_name"],
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        client_id=cfg.client_id if cfg else None,
        client_secret=cfg.client_secret if cfg else None,
    )
    now = datetime.now()
    events = connector.fetch_busy(now, now + timedelta(days=config.get("days", 120)))
    model = merge_events(CoverageModelIn(**model_cfg), config["caregiver_name"],
                         events, source_prefix="msgraph_")
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {"synced_busy_events": len(events)}


def _replay_ics(store, family_id: str, profile: dict, config: dict) -> dict:
    model_cfg = profile.get("coverage_model")
    if not model_cfg:
        return {"skipped": "no coverage model"}
    connector = ICSCalendarConnector(
        config["url"], attendees=tuple(config["attendees"]),
        tz=config.get("tz", "America/Chicago"),
    )
    events = connector.fetch_busy()
    holder = config.get("holder") or config["attendees"][0]
    model = merge_events(CoverageModelIn(**model_cfg), holder, events, source_prefix="ics_")
    store.set_profile(family_id, coverage_model=model.model_dump(mode="json"))
    return {"synced_busy_events": len(events)}


def run_cycle(store, extractor, notifier=None) -> dict:
    """One full pass over every family: replay remembered syncs, report results.

    Never raises for a family's failure — each unit is caught individually so a
    broken feed can't stall the rest. When a ``notifier`` is supplied, the pass
    ends with a notification cycle — freshly synced data is exactly when new
    🔴 items appear, so the alert email goes out the same beat.
    """

    report: dict = {"started_at": datetime.now().isoformat(), "families": {}}
    for family_id in store.family_ids():
        profile = store.profile(family_id)
        family_report: dict = {}
        units: list[tuple[str, callable]] = [
            ("gmail", lambda p=profile: _sync_gmail(store, family_id, p, extractor)),
        ]
        configs = profile.get("sync_configs") or {}
        if configs.get("gcal"):
            units.append(("gcal", lambda p=profile, c=configs["gcal"]:
                          _replay_calendar(store, family_id, p, c)))
        if configs.get("outlook"):
            units.append(("outlook", lambda p=profile, c=configs["outlook"]:
                          _replay_outlook(store, family_id, p, c)))
        for i, ics_cfg in enumerate(configs.get("ics") or []):
            units.append((f"ics_{i}", lambda p=profile, c=ics_cfg:
                          _replay_ics(store, family_id, p, c)))

        for name, unit in units:
            try:
                family_report[name] = unit()
            except Exception as exc:  # noqa: BLE001 — isolate every failure
                log.warning("auto-sync %s/%s failed: %s", family_id, name, exc)
                family_report[name] = {"error": str(exc)}
        report["families"][family_id] = family_report

    if notifier is not None:
        from exhale.notify import run_notification_cycle

        try:
            report["notifications"] = run_notification_cycle(store, notifier)
        except Exception as exc:  # noqa: BLE001 — alerts must never break syncing
            log.warning("notification cycle failed: %s", exc)
            report["notifications"] = {"error": str(exc)}
    return report


class AutoSyncScheduler:
    """A daemon thread that runs :func:`run_cycle` every ``interval_minutes``."""

    def __init__(self, store, extractor, interval_minutes: float, notifier=None) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        self.store = store
        self.extractor = extractor
        self.notifier = notifier
        self.interval_minutes = interval_minutes
        self.cycles_run = 0
        self.last_report: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_minutes * 60):
            try:
                self.last_report = run_cycle(self.store, self.extractor,
                                             notifier=self.notifier)
            except Exception:  # noqa: BLE001 — the loop itself must survive
                log.exception("auto-sync cycle crashed")
            self.cycles_run += 1

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="exhale-auto-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def scheduler_from_env(store, extractor) -> AutoSyncScheduler | None:
    """Build (and start) the scheduler when EXHALE_AUTO_SYNC_MINUTES is set."""

    import os

    raw = os.environ.get("EXHALE_AUTO_SYNC_MINUTES", "").strip()
    try:
        minutes = float(raw) if raw else 0.0
    except ValueError:
        minutes = 0.0
    if minutes <= 0:
        return None
    from exhale.notify import notifier_from_env

    scheduler = AutoSyncScheduler(store, extractor, minutes,
                                  notifier=notifier_from_env())
    scheduler.start()
    return scheduler
