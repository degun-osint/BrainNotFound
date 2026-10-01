"""Group analyses stored per quiz and group, with the papers they were made from.

The single quizzes.class_analysis_result mixed every group (and every
organization of a shared quiz): existing results are kept as "all papers"
analyses, shown only to someone who can see all those papers.

Revision ID: 018_quiz_analyses
Revises: 017_generator_drafts
Create Date: 2026-10-01
"""
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '018_quiz_analyses'
down_revision = '017_generator_drafts'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'quiz_analyses' not in sa.inspect(bind).get_table_names():
        op.create_table(
            'quiz_analyses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('quiz_id', sa.Integer(), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
            sa.Column('response_ids', sa.JSON(), nullable=False),
            sa.Column('result', sa.JSON(), nullable=False),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_quiz_analyses_quiz_id', 'quiz_analyses', ['quiz_id'])
        op.create_index('ix_quiz_analyses_group_id', 'quiz_analyses', ['group_id'])

    analyses = sa.table('quiz_analyses', sa.column('quiz_id'), sa.column('group_id'), sa.column('response_ids', sa.JSON),
                        sa.column('result', sa.JSON), sa.column('created_at'))
    for quiz_id, result in bind.execute(sa.text(
            'SELECT id, class_analysis_result FROM quizzes WHERE class_analysis_result IS NOT NULL')).fetchall():
        ids = [row[0] for row in bind.execute(sa.text(
            'SELECT id FROM quiz_responses WHERE quiz_id = :q AND (is_test = 0 OR is_test IS NULL)'), {'q': quiz_id})]
        if isinstance(result, str):
            result = json.loads(result)
        op.bulk_insert(analyses, [{'quiz_id': quiz_id, 'group_id': None, 'response_ids': ids, 'result': result,
                                   'created_at': None}])


def downgrade():
    op.drop_table('quiz_analyses')
