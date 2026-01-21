"""Add monthly AI limits and subscription expiration to tenants.

Revision ID: 008_tenant_limits
Revises: 007_tenants
Create Date: 2026-01-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_tenant_limits'
down_revision = '007_tenants'
branch_labels = None
depends_on = None


def upgrade():
    # Add monthly limits columns
    op.add_column('tenants', sa.Column('monthly_ai_corrections', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('monthly_quiz_generations', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('monthly_class_analyses', sa.Integer(), nullable=True, server_default='0'))

    # Add usage counters
    op.add_column('tenants', sa.Column('used_ai_corrections', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('used_quiz_generations', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('used_class_analyses', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('usage_reset_date', sa.Date(), nullable=True))

    # Add subscription expiration
    op.add_column('tenants', sa.Column('subscription_expires_at', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('tenants', 'subscription_expires_at')
    op.drop_column('tenants', 'usage_reset_date')
    op.drop_column('tenants', 'used_class_analyses')
    op.drop_column('tenants', 'used_quiz_generations')
    op.drop_column('tenants', 'used_ai_corrections')
    op.drop_column('tenants', 'monthly_class_analyses')
    op.drop_column('tenants', 'monthly_quiz_generations')
    op.drop_column('tenants', 'monthly_ai_corrections')
