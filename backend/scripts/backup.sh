#!/usr/bin/env bash
# Encrypted logical backup of the BudgetAnalytics database.
#
#   PGHOST=... PGPORT=5432 PGUSER=... PGPASSWORD=... PGDATABASE=budget \
#   AGE_RECIPIENT=age1... BACKUP_DIR=/var/backups/budget scripts/backup.sh
#
# * pg_dump custom format (compressed, restorable table by table), streamed
#   straight into `age` encryption: no unencrypted dump touches the disk.
# * AGE_RECIPIENT is the PUBLIC key; the private key is kept offline/elsewhere
#   (a backup readable with keys stored next to it protects nothing).
# * Prints the file name and its SHA-256. Ship the file off-host (object
#   storage in another location) and apply the retention policy there.
set -euo pipefail
umask 077

: "${PGDATABASE:?set PGDATABASE}"
: "${BACKUP_DIR:?set BACKUP_DIR}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -n "${AGE_RECIPIENT:-}" ]]; then
  out="$BACKUP_DIR/${PGDATABASE}-${stamp}.dump.age"
  pg_dump --format=custom --no-owner --no-privileges "$PGDATABASE" \
    | age --encrypt --recipient "$AGE_RECIPIENT" --output "$out"
elif [[ "${ALLOW_UNENCRYPTED_BACKUP:-}" == "1" ]]; then
  # Local drills only. Never use for real data.
  out="$BACKUP_DIR/${PGDATABASE}-${stamp}.dump"
  pg_dump --format=custom --no-owner --no-privileges --file "$out" "$PGDATABASE"
else
  echo "Refusing to write an unencrypted backup: set AGE_RECIPIENT" >&2
  exit 2
fi

sha256sum "$out" | tee "$out.sha256"
