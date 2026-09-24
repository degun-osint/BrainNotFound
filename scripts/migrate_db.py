"""Container start: bring the database schema up to date (see app/utils/db_schema.py)."""
import os
import sys

# The schema may be outdated: don't let the backup scheduler query it
os.environ['SKIP_BACKUP_SCHEDULER'] = '1'

from app import create_app  # noqa: E402
from app.utils.db_schema import SchemaError, upgrade_schema  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        try:
            print(upgrade_schema())
        except SchemaError as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
