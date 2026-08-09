#!/usr/bin/env bash
# Exhale — pull-and-rebuild deploy, safe to run any time (and from cron).
#
#   ./scripts/deploy.sh          # update now if there's anything new
#
# Checks the branch's remote; if nothing new, exits quietly (a cron running
# this every 10 minutes costs nothing). If there are new commits: fast-forward
# pull, rebuild, restart, and prune old images so the disk never silently
# fills with build layers (a real risk on a small droplet).
#
# Fast-forward ONLY: if the server's copy has diverged (someone edited files
# on the box), this refuses rather than merging surprises into production.

set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

git fetch origin "$BRANCH" --quiet

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
	exit 0  # nothing new — stay quiet so cron logs stay readable
fi

echo "[$(date -Is)] deploying: $(git log --oneline -1 "$REMOTE" | head -1)"
git pull --ff-only --quiet
$COMPOSE up -d --build
docker image prune -f > /dev/null
echo "[$(date -Is)] deployed $(git rev-parse --short HEAD) — containers:"
$COMPOSE ps --format '{{.Name}} {{.Status}}' | sed 's/^/  /'
