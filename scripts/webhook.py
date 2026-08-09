#!/usr/bin/env python3
"""Deploy webhook — GitHub pings this the moment a push lands.

Runs on the HOST, not in Docker: rebuilding the stack means driving
`docker compose`, which a container cannot do for the containers around it
(short of mounting the Docker socket, which hands root on the host to
anything that gets into the container — not a trade worth making to save a
polling loop).

Standard library only, so there is nothing to install and nothing to keep
patched. Binds to localhost; Caddy terminates TLS and proxies to it.

Security posture, in order of what actually protects this:

* Every request must carry a valid ``X-Hub-Signature-256`` HMAC over the raw
  body, compared in constant time. No signature, wrong signature, or no
  configured secret → 403, and nothing runs.
* Only ``push`` events for the configured branch deploy. Pings answer 200
  (so GitHub's "test delivery" goes green) but do nothing.
* The deploy runs detached with a hard timeout, so a wedged build can't pile
  up workers or hold GitHub's connection open.
* One deploy at a time — concurrent pushes collapse into a single run rather
  than racing each other through the same working tree.

Configuration (environment):
    EXHALE_WEBHOOK_SECRET   required — the same value set in GitHub
    EXHALE_WEBHOOK_PORT     default 9000
    EXHALE_REPO_DIR         default /root/Exhale
    EXHALE_DEPLOY_BRANCH    default: whatever the repo is currently on
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger("exhale.webhook")

SECRET = os.environ.get("EXHALE_WEBHOOK_SECRET", "")
PORT = int(os.environ.get("EXHALE_WEBHOOK_PORT", "9000"))
REPO_DIR = os.environ.get("EXHALE_REPO_DIR", "/root/Exhale")
BRANCH = os.environ.get("EXHALE_DEPLOY_BRANCH", "")
MAX_BODY = 1 << 20  # GitHub push payloads are small; refuse anything absurd
DEPLOY_TIMEOUT = 900  # 15 minutes — a build that hangs must not hang forever

_deploying = threading.Lock()


def _current_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", REPO_DIR, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 — fall back to accepting any branch
        return ""


def _run_deploy() -> None:
    """Run deploy.sh once; extra triggers while busy are dropped on purpose."""

    if not _deploying.acquire(blocking=False):
        log.info("deploy already running — skipping this trigger")
        return
    try:
        log.info("deploying…")
        result = subprocess.run(
            [os.path.join(REPO_DIR, "scripts", "deploy.sh")],
            capture_output=True, text=True, timeout=DEPLOY_TIMEOUT,
        )
        for line in (result.stdout or "").splitlines():
            log.info("  %s", line)
        if result.returncode != 0:
            log.error("deploy failed (%s): %s", result.returncode,
                      (result.stderr or "").strip()[:2000])
        else:
            log.info("deploy finished")
    except subprocess.TimeoutExpired:
        log.error("deploy timed out after %ss", DEPLOY_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — the listener must survive
        log.exception("deploy crashed: %s", exc)
    finally:
        _deploying.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "ExhaleDeploy/1.0"

    def log_message(self, fmt, *args):  # quieter default access logging
        log.debug(fmt, *args)

    def _reply(self, code: int, message: str) -> None:
        body = message.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's contract
        if not SECRET:
            log.error("no EXHALE_WEBHOOK_SECRET set — refusing every delivery")
            return self._reply(403, "not configured")

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._reply(400, "bad body")
        raw = self.rfile.read(length)

        sent = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sent, expected):
            log.warning("rejected delivery with a bad signature")
            return self._reply(403, "bad signature")

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return self._reply(200, "pong")
        if event != "push":
            return self._reply(200, f"ignored {event}")

        try:
            payload = json.loads(raw)
        except ValueError:
            return self._reply(400, "bad json")

        ref = str(payload.get("ref") or "")
        wanted = BRANCH or _current_branch()
        if wanted and ref != f"refs/heads/{wanted}":
            return self._reply(200, f"ignored {ref}")

        # Answer immediately; GitHub times out deliveries that wait on a build.
        threading.Thread(target=_run_deploy, daemon=True).start()
        return self._reply(202, "deploying")

    def do_GET(self) -> None:  # noqa: N802
        self._reply(200, "exhale deploy webhook")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if not SECRET:
        log.error("EXHALE_WEBHOOK_SECRET is not set — every delivery will 403")
    log.info("listening on 127.0.0.1:%s (repo %s, branch %s)",
             PORT, REPO_DIR, BRANCH or _current_branch() or "any")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
