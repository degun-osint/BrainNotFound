"""Voice reading of the interview: per-interview mode/voice/rate, per-learner toggle.

Synthesis happens in the browser (Web Speech API), so nothing is stored but
the settings: the interview says whether the voice is offered, forced or off,
and the learner's own choice follows them from one device to the next.

Revision ID: 019_interview_tts
Revises: 018_quiz_analyses
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '019_interview_tts'
down_revision = '018_quiz_analyses'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    existing = {c['name'] for c in inspector.get_columns('interviews')}
    if 'tts_mode' not in existing:
        op.add_column('interviews', sa.Column('tts_mode', sa.String(length=10), nullable=True,
                                              server_default='optional'))
    if 'tts_voice_hint' not in existing:
        op.add_column('interviews', sa.Column('tts_voice_hint', sa.String(length=100), nullable=True))
    if 'tts_rate' not in existing:
        op.add_column('interviews', sa.Column('tts_rate', sa.Float(), nullable=True,
                                              server_default='1.0'))

    existing = {c['name'] for c in inspector.get_columns('users')}
    if 'tts_enabled' not in existing:
        op.add_column('users', sa.Column('tts_enabled', sa.Boolean(), nullable=True,
                                         server_default=sa.false()))


def downgrade():
    op.drop_column('users', 'tts_enabled')
    op.drop_column('interviews', 'tts_rate')
    op.drop_column('interviews', 'tts_voice_hint')
    op.drop_column('interviews', 'tts_mode')
