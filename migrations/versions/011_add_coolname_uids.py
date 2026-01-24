"""Add coolname-based UIDs to all URL-accessed models.

This migration adds a 'uid' column to models that are accessed via URLs,
allowing for user-friendly identifiers like 'brave-purple-tiger' instead
of numeric IDs.

The uid column is initially nullable to allow data migration for existing
records. A separate migration will make it NOT NULL after all records
have been populated with UIDs.

Revision ID: 011_coolname_uids
Revises: 010_quota_alerts
Create Date: 2026-01-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_coolname_uids'
down_revision = '010_quota_alerts'
branch_labels = None
depends_on = None


def upgrade():
    # Add uid columns (nullable initially for data migration)

    # Quiz - main quiz entity
    op.add_column('quizzes',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_quizzes_uid', 'quizzes', ['uid'], unique=True)

    # Interview - interview configuration
    op.add_column('interviews',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_interviews_uid', 'interviews', ['uid'], unique=True)

    # Group - user groups
    op.add_column('groups',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_groups_uid', 'groups', ['uid'], unique=True)

    # User - user accounts
    op.add_column('users',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_users_uid', 'users', ['uid'], unique=True)

    # QuizResponse - student quiz submissions
    op.add_column('quiz_responses',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_quiz_responses_uid', 'quiz_responses', ['uid'], unique=True)

    # InterviewSession - student interview sessions
    op.add_column('interview_sessions',
        sa.Column('uid', sa.String(100), nullable=True))
    op.create_index('ix_interview_sessions_uid', 'interview_sessions', ['uid'], unique=True)


def downgrade():
    # Drop in reverse order

    op.drop_index('ix_interview_sessions_uid', table_name='interview_sessions')
    op.drop_column('interview_sessions', 'uid')

    op.drop_index('ix_quiz_responses_uid', table_name='quiz_responses')
    op.drop_column('quiz_responses', 'uid')

    op.drop_index('ix_users_uid', table_name='users')
    op.drop_column('users', 'uid')

    op.drop_index('ix_groups_uid', table_name='groups')
    op.drop_column('groups', 'uid')

    op.drop_index('ix_interviews_uid', table_name='interviews')
    op.drop_column('interviews', 'uid')

    op.drop_index('ix_quizzes_uid', table_name='quizzes')
    op.drop_column('quizzes', 'uid')
