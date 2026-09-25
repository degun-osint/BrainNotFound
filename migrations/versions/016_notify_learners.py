"""Per-quiz option: email learners when their grade is validated or their contest handled.

Revision ID: 016_notify_learners
Revises: 015_grading_trust
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016_notify_learners'
down_revision = '015_grading_trust'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('quizzes')}
    if 'notify_learners' not in existing:
        op.add_column('quizzes', sa.Column('notify_learners', sa.Boolean(), nullable=True, server_default=sa.true()))


def downgrade():
    op.drop_column('quizzes', 'notify_learners')
