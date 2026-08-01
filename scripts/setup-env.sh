#!/usr/bin/env bash
# Exhale — first-run .env setup.
#
# Generates the three secrets, fills in the deployment settings, and prints
# the two values you must save before going further. Safe to read before you
# run it; it only writes ./.env and never transmits anything.
#
# Usage:  ./scripts/setup-env.sh your.domain.com you@example.com
#
# Re-running is safe: an existing .env is left alone (rename it first if you
# really want a fresh one). This matters — regenerating EXHALE_MASTER_SECRET
# against an existing database locks every family out of their own data.

set -euo pipefail

DOMAIN="${1:-}"
TLS_EMAIL="${2:-}"

if [ -z "$DOMAIN" ]; then
	echo "usage: $0 <domain> [tls-email]" >&2
	echo "  e.g. $0 exhale.example.com you@example.com" >&2
	exit 1
fi

cd "$(dirname "$0")/.."

if [ -f .env ]; then
	echo "!! .env already exists — leaving it untouched."
	echo "   If you truly want to start over: mv .env .env.old && rerun."
	echo "   (Careful: a new master secret cannot decrypt existing data.)"
	exit 1
fi

cp .env.example .env

python3 - "$DOMAIN" "$TLS_EMAIL" <<'PY'
import pathlib, re, secrets, sys

domain, tls_email = sys.argv[1], sys.argv[2]

# Production posture: auth on, invite-only, hourly background sync.
values = {
    "EXHALE_MASTER_SECRET": secrets.token_urlsafe(48),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(16),
    "EXHALE_BOOTSTRAP_INVITE": secrets.token_urlsafe(12),
    "EXHALE_DOMAIN": domain,
    "EXHALE_TLS_EMAIL": tls_email,
    "EXHALE_REQUIRE_AUTH": "1",
    "EXHALE_INVITE_ONLY": "1",
    "EXHALE_AUTO_SYNC_MINUTES": "60",
}

path = pathlib.Path(".env")
text = path.read_text()
for key, value in values.items():
    text, n = re.subn(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", text)
    if n == 0:  # key absent from .env.example — append rather than lose it
        text += f"\n{key}={value}\n"
path.write_text(text)
path.chmod(0o600)  # secrets are readable only by this user

print()
print("=" * 66)
print("  SAVE THESE TWO IN YOUR PASSWORD MANAGER BEFORE YOU CONTINUE")
print("=" * 66)
print()
print("  EXHALE_MASTER_SECRET")
print(f"    {values['EXHALE_MASTER_SECRET']}")
print()
print("    This decrypts every family's data. It is deliberately NOT stored")
print("    in the database, and nobody — not DigitalOcean, not Anthropic,")
print("    not me — can recover it for you. Lose it and the data is gone.")
print("    That is the design, and it cuts both ways.")
print()
print("  EXHALE_BOOTSTRAP_INVITE")
print(f"    {values['EXHALE_BOOTSTRAP_INVITE']}")
print()
print("    Your signup code — you'll type this once to create your family.")
print()
print("=" * 66)
print()
print("Written to .env (permissions 600). Still unset, and fine for now:")
print("  EXHALE_GOOGLE_*   — 'Connect Google' (DEPLOY.md step 4)")
print("  ANTHROPIC_API_KEY — reading what plain rules can't (step 5)")
print("  EXHALE_SMTP_*     — critical-item email alerts (step 6, optional)")
print()
print("Exhale runs without them; those features just stay dark until set.")
PY
