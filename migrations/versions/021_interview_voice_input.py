"""Learner dictating their answers: provider settings, per-interview mode, consent.

Off by default everywhere. Dictation sends the learner's voice to a third
party, so an existing install must opt in deliberately, per interview, and
each learner consents once per session before the microphone works.

The recording itself is never stored, so there is no column for it: only the
transcript, in the message the learner chooses to send.

Revision ID: 021_interview_voice_input
Revises: 020_tts_provider
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '021_interview_voice_input'
down_revision = '020_tts_provider'
branch_labels = None
depends_on = None

SETTINGS_COLUMNS = (
    ('stt_provider', lambda: sa.Column('stt_provider', sa.String(length=30), nullable=True,
                                       server_default='none')),
    ('stt_base_url', lambda: sa.Column('stt_base_url', sa.String(length=255), nullable=True)),
    ('stt_model', lambda: sa.Column('stt_model', sa.String(length=100), nullable=True)),
    ('stt_api_key_encrypted', lambda: sa.Column('stt_api_key_encrypted', sa.Text(), nullable=True)),
)


def upgrade():
    inspector = sa.inspect(op.get_bind())

    existing = {c['name'] for c in inspector.get_columns('site_settings')}
    for name, column in SETTINGS_COLUMNS:
        if name not in existing:
            op.add_column('site_settings', column())

    if 'stt_mode' not in {c['name'] for c in inspector.get_columns('interviews')}:
        op.add_column('interviews', sa.Column('stt_mode', sa.String(length=10), nullable=True,
                                              server_default='off'))

    if 'voice_consent_at' not in {c['name'] for c in inspector.get_columns('interview_sessions')}:
        op.add_column('interview_sessions', sa.Column('voice_consent_at', sa.DateTime(), nullable=True))

    if 'from_voice' not in {c['name'] for c in inspector.get_columns('interview_messages')}:
        op.add_column('interview_messages', sa.Column('from_voice', sa.Boolean(), nullable=True,
                                                      server_default=sa.false()))


def downgrade():
    op.drop_column('interview_messages', 'from_voice')
    op.drop_column('interview_sessions', 'voice_consent_at')
    op.drop_column('interviews', 'stt_mode')
    for name, _ in reversed(SETTINGS_COLUMNS):
        op.drop_column('site_settings', name)
