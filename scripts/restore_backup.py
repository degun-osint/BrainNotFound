"""Restore a backup file from the command line, like Admin > Settings does.

Takes a pre-restore snapshot (kept in backups/), imports the dump, then brings
the schema up to date. Used by deploy.sh for the MySQL -> MariaDB switch.
Usage (inside the web container): python -m scripts.restore_backup /app/backups/<file>
"""
import os
import sys

os.environ['SKIP_BACKUP_SCHEDULER'] = '1'

from app import create_app  # noqa: E402
from app.utils.backup_manager import BackupManager  # noqa: E402
from app.utils.db_schema import upgrade_schema  # noqa: E402


def main(path):
    app = create_app()
    with app.app_context():
        ok, message = BackupManager().restore_backup(path)
        print(message)
        if not ok:
            return 1
        print(upgrade_schema())
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
