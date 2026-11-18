#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into an EMPTY database.
#
#   PGHOST=... PGUSER=... PGPASSWORD=... \
#   AGE_IDENTITY=/secure/key.txt scripts/restore.sh <backup-file> <target-db>
#
# Safety: refuses to restore into a database that already has tables, so a
# typo cannot overwrite production. Restore into a NEW database, verify it,
# then switch the application's DATABASE_URL to it (see docs/DEPLOYMENT.md).
set -euo pipefail

backup="${1:?usage: restore.sh <backup-file> <target-db>}"
target="${2:?usage: restore.sh <backup-file> <target-db>}"

if [[ -f "$backup.sha256" ]]; then
  sha256sum --check --status "$backup.sha256" || { echo "Checksum mismatch: $backup" >&2; exit 3; }
fi

existing="$(psql --dbname "$target" --tuples-only --no-align \
  --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [[ "$existing" != "0" ]]; then
  echo "Refusing to restore: database '$target' is not empty ($existing tables)" >&2
  exit 4
fi

if [[ "$backup" == *.age ]]; then
  : "${AGE_IDENTITY:?set AGE_IDENTITY to the private key file}"
  age --decrypt --identity "$AGE_IDENTITY" "$backup" \
    | pg_restore --no-owner --no-privileges --exit-on-error --dbname "$target"
else
  pg_restore --no-owner --no-privileges --exit-on-error --dbname "$target" "$backup"
fi

echo "Restored into '$target'. Alembic revision:"
psql --dbname "$target" --tuples-only --no-align --command "SELECT version_num FROM alembic_version"
