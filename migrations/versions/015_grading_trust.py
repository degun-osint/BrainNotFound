"""Grading trust: review mode, graders, contests, publication date.

Revision ID: 015_grading_trust
Revises: 014_fill_null_defaults
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_grading_trust'
down_revision = '014_fill_null_defaults'
branch_labels = None
depends_on = None

QUIZ_COLUMNS = [
    ('grading_mode', sa.String(10), 'direct'),
    ('contest_days', sa.Integer(), '7'),
    ('digest_pending_since', sa.DateTime(), None),
    ('digest_sent_at', sa.DateTime(), None),
]
RESPONSE_COLUMNS = [
    ('graded_at', sa.DateTime()),
    ('reviewed_at', sa.DateTime()),
    ('review_reason', sa.String(10)),
]


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    existing = _columns('quizzes')
    for name, type_, default in QUIZ_COLUMNS:
        if name not in existing:
            op.add_column('quizzes', sa.Column(name, type_, nullable=True, server_default=default))

    existing = _columns('quiz_responses')
    for name, type_ in RESPONSE_COLUMNS:
        if name not in existing:
            op.add_column('quiz_responses', sa.Column(name, type_, nullable=True))
    if 'reviewed_by_id' not in existing:
        op.add_column('quiz_responses', sa.Column('reviewed_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_quiz_responses_reviewed_by', 'quiz_responses', 'users',
                              ['reviewed_by_id'], ['id'], ondelete='SET NULL')

    # Papers already graded: their grade was published when they were submitted
    op.execute("UPDATE quiz_responses SET graded_at = submitted_at "
               "WHERE graded_at IS NULL AND grading_status = 'completed'")
    # Papers already waiting were held back because the AI could not grade them
    op.execute("UPDATE quiz_responses SET review_reason = 'ai' "
               "WHERE review_reason IS NULL AND grading_status = 'review'")

    tables = _tables()
    if 'quiz_graders' not in tables:
        op.create_table(
            'quiz_graders',
            sa.Column('quiz_id', sa.Integer(), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        )
    if 'answer_contests' not in tables:
        op.create_table(
            'answer_contests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('answer_id', sa.Integer(), sa.ForeignKey('answers.id', ondelete='CASCADE'),
                      nullable=False, unique=True),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('status', sa.String(10), nullable=False, server_default='open'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('reply', sa.Text(), nullable=True),
            sa.Column('score_before', sa.Float(), nullable=True),
            sa.Column('score_after', sa.Float(), nullable=True),
            sa.Column('resolved_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_answer_contests_status', 'answer_contests', ['status'])


def downgrade():
    op.drop_table('answer_contests')
    op.drop_table('quiz_graders')
    op.drop_constraint('fk_quiz_responses_reviewed_by', 'quiz_responses', type_='foreignkey')
    for name in ('reviewed_by_id', 'review_reason', 'reviewed_at', 'graded_at'):
        op.drop_column('quiz_responses', name)
    for name, _, _ in reversed(QUIZ_COLUMNS):
        op.drop_column('quizzes', name)
