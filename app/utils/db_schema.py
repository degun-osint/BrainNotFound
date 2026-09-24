"""Bring the database schema up to date, deterministically.

Used at container start (scripts/migrate_db.py) and right after a backup
restore, since a restored dump carries the schema and alembic revision of
the day it was taken.

- Empty database: create every table from the models, then stamp head.
- Revision known to this repository: regular `alembic upgrade head`.
- Unknown revision: the old entrypoint auto-generated migrations inside the
  container, so the stored revision often exists nowhere in the repo. Its
  schema then matches the models of the last release before this module,
  i.e. revision 011. If that is confirmed, stamp 011 and upgrade from there;
  otherwise refuse, rather than auto-generating a diff that could drop data.

Never drops alembic_version, never generates migrations at runtime.
Must run inside an app context.
"""
from alembic.script import ScriptDirectory
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect, text

from app import db, migrate

LEGACY_BASELINE = '011_coolname_uids'


class SchemaError(Exception):
    """The schema is in a state we refuse to migrate automatically."""


def _current_revision(tables):
    if 'alembic_version' not in tables:
        return None
    row = db.session.execute(text('SELECT version_num FROM alembic_version')).first()
    return row[0] if row else None


def _matches_legacy_baseline(inspector):
    """Revision 011 added quizzes.uid; 010 added the quota alert columns."""
    quiz_columns = {c['name'] for c in inspector.get_columns('quizzes')}
    tenant_columns = {c['name'] for c in inspector.get_columns('tenants')}
    return 'uid' in quiz_columns and 'quota_alert_enabled' in tenant_columns


def upgrade_schema():
    """Create or upgrade the schema. Returns a short description of what was done."""
    db.session.remove()
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if 'users' not in tables:
        db.create_all()
        stamp(revision='head')
        return 'Empty database: schema created from models'

    script = ScriptDirectory.from_config(migrate.get_config())
    known = {rev.revision for rev in script.walk_revisions()}
    revision = _current_revision(tables)
    db.session.remove()

    done = ''
    if revision not in known:
        if not _matches_legacy_baseline(inspector):
            raise SchemaError(
                f'Database revision {revision!r} is unknown and the schema does not match '
                f'{LEGACY_BASELINE}. Check the schema manually, run `flask db stamp <revision>`, '
                f'then restart.')
        stamp(revision=LEGACY_BASELINE, purge=True)
        done = f'Unknown revision {revision!r} stamped as {LEGACY_BASELINE}. '

    upgrade()
    return done + 'Schema up to date'
