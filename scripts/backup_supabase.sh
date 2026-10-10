#!/usr/bin/env bash
# Run against an already linked Supabase CLI project. Never logs credentials.
set -euo pipefail
umask 077
if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/backup_supabase.sh LINKED_PROJECT_DIRECTORY BACKUP_DIRECTORY' >&2
  exit 2
fi
command -v supabase >/dev/null
command -v docker >/dev/null
docker info >/dev/null 2>&1 || { echo 'Docker must be running before exporting.' >&2; exit 1; }
backup_parent=$(realpath -m "$2")
mkdir -p "$backup_parent"
backup_directory=$(mktemp -d "$backup_parent/devspace-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
echo "Export directory: $backup_directory"
echo 'An export is incomplete unless COMPLETE exists.'
supabase db dump --linked --workdir "$1" --role-only --file "$backup_directory/roles.sql"
supabase db dump --linked --workdir "$1" --file "$backup_directory/schema.sql"
supabase db dump --linked --workdir "$1" --data-only --use-copy --file "$backup_directory/data.sql"
for file in roles schema data; do
  test -s "$backup_directory/$file.sql"
done
(cd "$backup_directory" && sha256sum roles.sql schema.sql data.sql > SHA256SUMS)
cat > "$backup_directory/README.txt" <<'EOF'
Supabase logical export: roles, application schema, and database data.
Contains sensitive data: keep private and encrypt before uploading off-site.
Storage object file contents are NOT included. Back these up separately.
Custom auth/storage schema changes, migrations, encryption keys and project
settings may require separate migration artifacts/configuration.
Custom login passwords must be reset when restoring.
Three dumps are separate snapshots: run during a quiet period or pause writers
when cross-file consistency is required.
COMPLETE means the export commands succeeded, not that a restore was tested.
Validate by restoring into a separate test database before relying on it.
Official instructions:
https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore
EOF
touch "$backup_directory/COMPLETE"
echo 'Export complete. Copy privately off-site and verify SHA256SUMS there.'
