"""Add editable LLM provider, base URL, model and API key to site settings.

Revision ID: 012_ai_settings
Revises: 011_coolname_uids
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_ai_settings'
down_revision = '011_coolname_uids'
branch_labels = None
depends_on = None

COLUMNS = [
    ('ai_provider', sa.String(30)),
    ('ai_base_url', sa.String(255)),
    ('ai_model', sa.String(100)),
    ('ai_api_key_encrypted', sa.Text()),
]


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('site_settings')}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column('site_settings', sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _ in reversed(COLUMNS):
        op.drop_column('site_settings', name)
