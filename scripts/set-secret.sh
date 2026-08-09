#!/usr/bin/env bash
# Exhale — set one value in .env without hand-editing it.
#
# Usage:  ./scripts/set-secret.sh ANTHROPIC_API_KEY
#         (then paste the value when prompted)
#
# Why a script: pasting into nano inside a browser console is where these go
# wrong — a value that arrives with a trailing space or a missing last
# character fails later with an unhelpful error, far from the cause. This
# reads the value straight into a variable, strips surrounding whitespace,
# and writes exactly one line.
#
# Sensitive values (KEY/SECRET/PASSWORD/TOKEN in the name) are read without
# echoing and confirmed masked. Everything else — a redirect URI, a domain —
# is shown in full, because for those seeing it IS the check.

set -euo pipefail

KEY="${1:-}"
if [ -z "$KEY" ]; then
	echo "usage: $0 <ENV_VAR_NAME>" >&2
	echo "  e.g. $0 ANTHROPIC_API_KEY" >&2
	exit 1
fi

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
	echo "!! No .env here. Run ./scripts/setup-env.sh first." >&2
	exit 1
fi

case "$KEY" in
	*KEY|*SECRET|*PASSWORD|*TOKEN) SENSITIVE=1 ;;
	*) SENSITIVE=0 ;;
esac

if [ "$SENSITIVE" = "1" ]; then
	printf 'Paste the value for %s, then press Enter.\n' "$KEY"
	printf 'NOTE: nothing appears on screen as you paste — no dots, no cursor\n'
	printf 'movement. That is correct. Paste ONCE, then press Enter.\n> '
	read -rs VALUE
	echo
else
	printf 'Paste the value for %s, then press Enter:\n> ' "$KEY"
	read -r VALUE
fi

VALUE="$(printf '%s' "$VALUE" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [ -z "$VALUE" ]; then
	echo "!! Empty value — nothing written." >&2
	exit 1
fi

KEY="$KEY" VALUE="$VALUE" SENSITIVE="$SENSITIVE" python3 - <<'PY'
import os, pathlib, re

key, value = os.environ["KEY"], os.environ["VALUE"]
path = pathlib.Path(".env")
text = path.read_text()

line = f"{key}={value}"
text, n = re.subn(rf"(?m)^{re.escape(key)}=.*$", lambda _: line, text)
if n == 0:
    if not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
path.write_text(text)
path.chmod(0o600)

def repeated_unit(text: str) -> str | None:
    """Return the unit if `text` is the same string pasted N>1 times.

    Hidden input shows nothing as you paste, so pasting again "because it
    didn't take" is the single easiest mistake to make here — and the result
    is a value that looks fine but authenticates against nothing.
    """

    for size in range(1, len(text) // 2 + 1):
        if len(text) % size == 0 and text[:size] * (len(text) // size) == text:
            return text[:size]
    return None

if os.environ["SENSITIVE"] == "1":
    shown = value[:6] + "…" + value[-4:] if len(value) > 14 else "(short value)"
    print(f"\n✓ {key} set — {shown}  ({len(value)} characters)")
    unit = repeated_unit(value)
    if unit:
        print(f"\n  !! That looks like the same {len(unit)}-character value pasted "
              f"{len(value) // len(unit)} times.")
        print("     Nothing shows on screen while pasting — it did take the first")
        print("     time. Re-run this command and paste exactly once.")
    else:
        print("  Check that length looks right; a truncated paste is the usual bug.")
else:
    print(f"\n✓ {key} = {value}")

print("\nRestart to pick it up:")
print("  docker compose -f docker-compose.prod.yml up -d")
PY
