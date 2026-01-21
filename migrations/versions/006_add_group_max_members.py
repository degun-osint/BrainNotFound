"""Add max_members to groups table.

Revision ID: 006_group_max_members
Revises: 005_pages
Create Date: 2026-01-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_group_max_members'
down_revision = '005_pages'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('groups', sa.Column('max_members', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('groups', 'max_members')
