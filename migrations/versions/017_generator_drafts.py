"""Generator drafts: course text kept 24 h to regenerate chosen questions.

Revision ID: 017_generator_drafts
Revises: 016_notify_learners
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '017_generator_drafts'
down_revision = '016_notify_learners'
branch_labels = None
depends_on = None


def upgrade():
    if 'generator_drafts' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'generator_drafts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('difficulty', sa.String(20), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('content', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql', 'mariadb'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_generator_drafts_token', 'generator_drafts', ['token'], unique=True)
    op.create_index('ix_generator_drafts_created_at', 'generator_drafts', ['created_at'])


def downgrade():
    op.drop_table('generator_drafts')
