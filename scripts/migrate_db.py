"""Bring the database schema up to date, deterministically.

- Empty database: create every table from the models, then stamp head.
- Revision known to this repository: regular `alembic upgrade head`.
- Unknown revision: the previous entrypoint auto-generated migrations inside
  the container, so the stored revision often exists nowhere in the repo.
  Its schema then matches the models of the last release before this script,
  i.e. revision 011. If that is confirmed, stamp 011 and upgrade from there;
  otherwise stop and let a human look, rather than auto-generating a diff
  that could drop tables or columns.

Never drops alembic_version, never generates migrations at runtime.
"""
import os
import sys

from alembic.script import ScriptDirectory
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect, text

# The schema may be outdated: don't let the backup scheduler query it
os.environ['SKIP_BACKUP_SCHEDULER'] = '1'

from app import create_app, db, migrate  # noqa: E402

app = create_app()

LEGACY_BASELINE = '011_coolname_uids'


def current_revision(tables):
    if 'alembic_version' not in tables:
        return None
    row = db.session.execute(text('SELECT version_num FROM alembic_version')).first()
    return row[0] if row else None


def matches_legacy_baseline(inspector):
    """Revision 011 added quizzes.uid; 010 added the quota alert columns."""
    quiz_columns = {c['name'] for c in inspector.get_columns('quizzes')}
    tenant_columns = {c['name'] for c in inspector.get_columns('tenants')}
    return 'uid' in quiz_columns and 'quota_alert_enabled' in tenant_columns


def main():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        if 'users' not in tables:
            print('Empty database: creating schema from models')
            db.create_all()
            stamp(revision='head')
            return 0

        script = ScriptDirectory.from_config(migrate.get_config())
        known = {rev.revision for rev in script.walk_revisions()}
        revision = current_revision(tables)

        if revision not in known:
            if not matches_legacy_baseline(inspector):
                print(f'ERROR: database revision {revision!r} is unknown and the schema does not '
                      f'match {LEGACY_BASELINE}. Refusing to guess: check the schema manually, '
                      f'then run `flask db stamp <revision>` and restart.', file=sys.stderr)
                return 1
            print(f'Unknown revision {revision!r}, schema matches {LEGACY_BASELINE}: stamping it')
            stamp(revision=LEGACY_BASELINE, purge=True)

        upgrade()
        return 0


if __name__ == '__main__':
    sys.exit(main())
