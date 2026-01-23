"""Add quota alert settings to tenants.

Revision ID: 010_quota_alerts
Revises: 009_interviews
Create Date: 2026-01-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010_quota_alerts'
down_revision = '009_interviews'
branch_labels = None
depends_on = None


def upgrade():
    # Add quota alert columns
    op.add_column('tenants', sa.Column('quota_alert_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('quota_alert_threshold', sa.Integer(), nullable=True, server_default='10'))
    op.add_column('tenants', sa.Column('quota_alert_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('tenants', 'quota_alert_sent_at')
    op.drop_column('tenants', 'quota_alert_threshold')
    op.drop_column('tenants', 'quota_alert_enabled')
