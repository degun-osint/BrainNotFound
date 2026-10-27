"""Server-side speech synthesis: provider settings next to the LLM ones.

'none' by default, so an install that says nothing keeps reading replies with
the voice of the learner's own browser (migration 019) and pays nothing.

Revision ID: 020_tts_provider
Revises: 019_interview_tts
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '020_tts_provider'
down_revision = '019_interview_tts'
branch_labels = None
depends_on = None

COLUMNS = (
    ('tts_provider', lambda: sa.Column('tts_provider', sa.String(length=30), nullable=True,
                                       server_default='none')),
    ('tts_base_url', lambda: sa.Column('tts_base_url', sa.String(length=255), nullable=True)),
    ('tts_model', lambda: sa.Column('tts_model', sa.String(length=100), nullable=True)),
    ('tts_voice', lambda: sa.Column('tts_voice', sa.String(length=100), nullable=True)),
    ('tts_api_key_encrypted', lambda: sa.Column('tts_api_key_encrypted', sa.Text(), nullable=True)),
)


def upgrade():
    inspector = sa.inspect(op.get_bind())

    existing = {c['name'] for c in inspector.get_columns('site_settings')}
    for name, column in COLUMNS:
        if name not in existing:
            op.add_column('site_settings', column())

    # The browser voice of 019 is a voice *name*; a provider wants its own voice id
    if 'tts_server_voice' not in {c['name'] for c in inspector.get_columns('interviews')}:
        op.add_column('interviews', sa.Column('tts_server_voice', sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column('interviews', 'tts_server_voice')
    for name, _ in reversed(COLUMNS):
        op.drop_column('site_settings', name)
