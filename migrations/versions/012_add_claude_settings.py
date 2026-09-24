"""Add editable Claude model and API key to site settings.

Revision ID: 012_claude_settings
Revises: 011_coolname_uids
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_claude_settings'
down_revision = '011_coolname_uids'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('site_settings')}
    if 'claude_model' not in existing:
        op.add_column('site_settings', sa.Column('claude_model', sa.String(100), nullable=True))
    if 'anthropic_api_key_encrypted' not in existing:
        op.add_column('site_settings', sa.Column('anthropic_api_key_encrypted', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('site_settings', 'anthropic_api_key_encrypted')
    op.drop_column('site_settings', 'claude_model')
