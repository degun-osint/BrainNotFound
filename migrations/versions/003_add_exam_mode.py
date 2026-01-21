"""Add exam mode and anti-cheat tracking fields

Revision ID: 003_exam_mode
Revises: 002_login_tracking
Create Date: 2026-01-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '003_exam_mode'
down_revision = '002_login_tracking'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add exam mode options to quizzes table
    with op.batch_alter_table('quizzes', schema=None) as batch_op:
        if not column_exists('quizzes', 'randomize_options'):
            batch_op.add_column(sa.Column('randomize_options', sa.Boolean(), nullable=True, default=False))
        if not column_exists('quizzes', 'one_question_per_page'):
            batch_op.add_column(sa.Column('one_question_per_page', sa.Boolean(), nullable=True, default=False))

    # Add anti-cheat tracking to quiz_responses table
    with op.batch_alter_table('quiz_responses', schema=None) as batch_op:
        if not column_exists('quiz_responses', 'focus_events'):
            batch_op.add_column(sa.Column('focus_events', sa.JSON(), nullable=True))
        if not column_exists('quiz_responses', 'total_focus_lost'):
            batch_op.add_column(sa.Column('total_focus_lost', sa.Integer(), nullable=True, default=0))
        if not column_exists('quiz_responses', 'ai_analysis_status'):
            batch_op.add_column(sa.Column('ai_analysis_status', sa.String(length=20), nullable=True))
        if not column_exists('quiz_responses', 'ai_analysis_result'):
            batch_op.add_column(sa.Column('ai_analysis_result', sa.JSON(), nullable=True))

    # Add time tracking to answers table
    with op.batch_alter_table('answers', schema=None) as batch_op:
        if not column_exists('answers', 'time_spent_seconds'):
            batch_op.add_column(sa.Column('time_spent_seconds', sa.Integer(), nullable=True))
        if not column_exists('answers', 'focus_lost_count'):
            batch_op.add_column(sa.Column('focus_lost_count', sa.Integer(), nullable=True, default=0))


def downgrade():
    with op.batch_alter_table('answers', schema=None) as batch_op:
        batch_op.drop_column('focus_lost_count')
        batch_op.drop_column('time_spent_seconds')

    with op.batch_alter_table('quiz_responses', schema=None) as batch_op:
        batch_op.drop_column('ai_analysis_result')
        batch_op.drop_column('ai_analysis_status')
        batch_op.drop_column('total_focus_lost')
        batch_op.drop_column('focus_events')

    with op.batch_alter_table('quizzes', schema=None) as batch_op:
        batch_op.drop_column('one_question_per_page')
        batch_op.drop_column('randomize_options')
