#!/bin/sh
# Exhale — nightly Postgres backup (runs inside the `backup` container).
#
# The database already stores only ciphertext: every household payload is
# AES-GCM encrypted under a per-family key derived from EXHALE_MASTER_SECRET,
# which is NOT in the database. So a dump contains no readable household data
# on its own — but it's still yours, so keep the backups volume private, and
# remember: a dump is useless without the master secret. Back that secret up
# separately (a password manager), or the encrypted data is unrecoverable.
#
# Writes one gzipped dump per day to /backups and prunes anything older than
# EXHALE_BACKUP_KEEP_DAYS. First run happens immediately, then every 24h.
set -eu

KEEP_DAYS="${EXHALE_BACKUP_KEEP_DAYS:-14}"
mkdir -p /backups

while true; do
	ts="$(date -u +%Y%m%d-%H%M%S)"
	out="/backups/exhale-${ts}.sql.gz"
	if pg_dump -h db -U postgres exhale | gzip > "${out}.tmp"; then
		mv "${out}.tmp" "$out"
		echo "[backup] wrote ${out}"
	else
		echo "[backup] FAILED at ${ts}" >&2
		rm -f "${out}.tmp"
	fi
	# Prune old dumps (never touches the just-written one).
	find /backups -name 'exhale-*.sql.gz' -type f -mtime "+${KEEP_DAYS}" -delete || true
	sleep 86400
done
