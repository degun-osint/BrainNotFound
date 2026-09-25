"""Container start: bring the database schema up to date (see app/utils/db_schema.py)."""
import os
import sys
import time

# The schema may be outdated: don't let the backup scheduler query it
os.environ['SKIP_BACKUP_SCHEDULER'] = '1'

from app import create_app  # noqa: E402
from app.utils.db_schema import SchemaError, upgrade_schema  # noqa: E402


def wait_for_database(timeout=90):
    """After a server reboot Docker starts db and web together (depends_on only
    applies to `docker compose up`): wait for MariaDB instead of crash-looping."""
    from sqlalchemy import text
    from app import db
    deadline = time.monotonic() + timeout
    while True:
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            return True
        except Exception as e:
            if time.monotonic() > deadline:
                print(f'ERROR: database unreachable after {timeout}s: {e}', file=sys.stderr)
                return False
            print('Waiting for the database...', flush=True)
            time.sleep(2)


def main():
    app = create_app()
    with app.app_context():
        if not wait_for_database():
            return 1
        try:
            print(upgrade_schema())
        except SchemaError as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
