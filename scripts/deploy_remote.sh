#!/bin/bash
# Run ON THE SERVER after the files are synced (called by deploy.sh).
# Builds while the site keeps running, restarts, waits for the app, and on a
# brand new database (MariaDB switch) re-imports the pre-deploy backup.
# Usage: deploy_remote.sh <app_dir> [pre-deploy backup, relative to app_dir]
set -euo pipefail
cd "$1"
BACKUP="${2:-}"

echo "Construction de l'image (le site reste en ligne)..."
docker compose build
echo "Redemarrage..."
docker compose up -d --remove-orphans

# Any HTTP answer means the app is up: with ALLOWED_HOSTS set in .env, a
# request to 127.0.0.1 gets a 403, which is fine here.
HEALTHCHECK='
import sys, urllib.request, urllib.error
try:
    urllib.request.urlopen("http://127.0.0.1:5000/login", timeout=5)
except urllib.error.HTTPError:
    pass
except Exception as e:
    sys.exit(str(e))
'
echo -n "Attente de l'application"
for i in $(seq 1 60); do
    if ERR=$(docker compose exec -T web python -c "$HEALTHCHECK" 2>&1 < /dev/null); then
        echo " : OK"
        break
    fi
    if [ "$i" = 60 ]; then
        echo " : ECHEC"
        echo "Derniere erreur : $ERR"
        docker compose logs --tail=40 web
        exit 1
    fi
    echo -n "."; sleep 3
done

# Background worker (AI grading, emails): warn, the site itself is up
if ! docker compose ps --status running --services | grep -x worker > /dev/null; then
    echo "ATTENTION : le worker ne tourne pas (corrections IA et emails en attente)"
    docker compose logs --tail=20 worker
fi

# A new database holds only the seeded admin: that's the MariaDB switch (or a
# first install). Re-import what the previous version had.
USERS=$(docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mariadb -N -uroot "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM users"' < /dev/null | tr -d '[:space:]')
if [ "${USERS:-0}" -le 1 ]; then
    # No backup from this run (e.g. re-running after an interrupted deploy):
    # fall back to the latest real pre-deploy backup (never an "emptydb" one)
    if [ -z "$BACKUP" ]; then
        BACKUP=$(ls -t backups/backup_predeploy_2*.sql.gz 2>/dev/null | head -1 || true)
    fi
    if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
        echo "Base neuve detectee : import de $BACKUP"
        docker compose exec -T web python -m scripts.restore_backup "/app/$BACKUP" < /dev/null
    else
        echo "Base neuve et aucune sauvegarde d'avant deploiement : rien a importer"
    fi
fi
