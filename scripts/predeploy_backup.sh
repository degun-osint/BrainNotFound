#!/bin/bash
# Run ON THE SERVER before new files are synced (deploy.sh pipes it over ssh).
# Dumps the running database into backups/, where it also shows up in
# Admin > Settings. Prints the dump path on the last line ("" if none).
# Usage: predeploy_backup.sh <app_dir>
set -euo pipefail
cd "$1"

if [ ! -f docker-compose.yml ] || ! docker compose ps --status running --services 2>/dev/null < /dev/null | grep -x db > /dev/null; then
    echo "Base non demarree : pas de sauvegarde (premier deploiement ?)" >&2
    echo ""
    exit 0
fi

mkdir -p backups
out="backups/backup_predeploy_$(date +%Y%m%d_%H%M%S).sql.gz"
# Works with the old MySQL container as with MariaDB (MYSQL_* comes from .env).
# < /dev/null: this script is itself read from stdin (ssh ... bash -s), and
# docker exec would otherwise swallow the rest of it.
docker compose exec -T db sh -c '
    DUMP=$(command -v mariadb-dump || command -v mysqldump)
    MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec "$DUMP" -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"
' < /dev/null | gzip > "$out"

# No grep -q: it stops early, gunzip gets SIGPIPE and pipefail reports a failure
if ! gunzip -c "$out" | grep 'CREATE TABLE `users`' > /dev/null; then
    echo "ERREUR : la sauvegarde $out est vide ou incomplete, deploiement annule" >&2
    exit 1
fi
echo "Sauvegarde : $out ($(du -h "$out" | cut -f1))" >&2
echo "$out"
