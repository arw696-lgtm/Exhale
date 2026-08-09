#!/usr/bin/env bash
# Install the deploy webhook: generate a secret, install the service, start it.
#
#   ./scripts/install-webhook.sh
#
# Prints the secret and the URL to paste into GitHub. Safe to re-run — it
# keeps an existing secret rather than minting a new one (a fresh secret
# would silently break the GitHub side until you updated it there too).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=/etc/exhale-webhook.env
UNIT=/etc/systemd/system/exhale-webhook.service

if [ "$(id -u)" != "0" ]; then
	echo "Run as root (this installs a systemd service)." >&2
	exit 1
fi

if [ -f "$ENV_FILE" ] && grep -q '^EXHALE_WEBHOOK_SECRET=' "$ENV_FILE"; then
	SECRET="$(grep '^EXHALE_WEBHOOK_SECRET=' "$ENV_FILE" | cut -d= -f2-)"
	echo "Keeping the existing webhook secret."
else
	SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
	cat > "$ENV_FILE" <<EOF
EXHALE_WEBHOOK_SECRET=$SECRET
EXHALE_REPO_DIR=$REPO_DIR
EXHALE_WEBHOOK_PORT=9000
EOF
	chmod 600 "$ENV_FILE"
	echo "Generated a new webhook secret."
fi

install -m 644 "$REPO_DIR/scripts/exhale-webhook.service" "$UNIT"
sed -i "s#/root/Exhale#$REPO_DIR#g" "$UNIT"
systemctl daemon-reload
systemctl enable --now exhale-webhook >/dev/null
sleep 1

DOMAIN="$(grep -E '^EXHALE_DOMAIN=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
DOMAIN="${DOMAIN:-YOUR_DOMAIN}"

echo
echo "================================================================"
echo "  Webhook installed. Add it in GitHub:"
echo "================================================================"
echo
echo "  Repo → Settings → Webhooks → Add webhook"
echo
echo "  Payload URL:   https://$DOMAIN/deploy-webhook"
echo "  Content type:  application/json"
echo "  Secret:        $SECRET"
echo "  Events:        Just the push event"
echo
echo "================================================================"
echo
systemctl is-active --quiet exhale-webhook \
	&& echo "Service is running. Logs: journalctl -u exhale-webhook -f" \
	|| echo "!! Service failed to start: journalctl -u exhale-webhook -n 30"
