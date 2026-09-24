"""Replace NULLs left by older migrations with the model defaults.

Columns added to existing tenants by migrations 008-010 had no server
default, so organizations created before them hold NULL where the code
expects 0 (quotas, usage counters) or 10 (quota alert threshold).

Revision ID: 014_fill_null_defaults
Revises: 013_drop_user_group_id
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_fill_null_defaults'
down_revision = '013_drop_user_group_id'
branch_labels = None
depends_on = None

DEFAULTS = {
    'tenants': {
        'max_users': 0, 'max_quizzes': 0, 'max_groups': 0, 'max_storage_mb': 0,
        'monthly_ai_corrections': 0, 'monthly_quiz_generations': 0,
        'monthly_class_analyses': 0, 'monthly_interviews': 0,
        'used_ai_corrections': 0, 'used_quiz_generations': 0,
        'used_class_analyses': 0, 'used_interviews': 0,
        'quota_alert_enabled': 0, 'quota_alert_threshold': 10,
    },
    'quiz_responses': {'is_test': 0},
}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, columns in DEFAULTS.items():
        existing = {c['name'] for c in inspector.get_columns(table)}
        for column, value in columns.items():
            if column in existing:
                bind.execute(sa.text(f'UPDATE {table} SET {column} = :v WHERE {column} IS NULL'), {'v': value})


def downgrade():
    pass  # NULL and the default mean the same thing for the application
