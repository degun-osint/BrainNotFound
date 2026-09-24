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

echo -n "Attente de l'application"
for i in $(seq 1 60); do
    if docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/login')" >/dev/null 2>&1 < /dev/null; then
        echo " : OK"
        break
    fi
    [ "$i" = 60 ] && { echo " : ECHEC"; docker compose logs --tail=40 web; exit 1; }
    echo -n "."; sleep 3
done

# A new database holds only the seeded admin: that's the MariaDB switch (or a
# first install). Re-import what the previous version had.
USERS=$(docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mariadb -N -uroot "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM users"' < /dev/null | tr -d '[:space:]')
if [ "${USERS:-0}" -le 1 ] && [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
    echo "Base neuve detectee : import de $BACKUP"
    docker compose exec -T web python -m scripts.restore_backup "/app/$BACKUP" < /dev/null
fi
