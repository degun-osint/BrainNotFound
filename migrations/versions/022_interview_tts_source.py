"""Which engine reads an interview's replies: the learner's browser, or the provider.

Until now an interview filled either a browser voice name or a provider voice id,
and nothing said which one would be used - the provider won whenever one was
configured. The choice is now explicit, and an interview can stay on the free
browser voice even where a provider exists.

'provider' by default: an install that configured one meant to use it.

Revision ID: 022_interview_tts_source
Revises: 021_interview_voice_input
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '022_interview_tts_source'
down_revision = '021_interview_voice_input'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('interviews')}
    if 'tts_source' not in existing:
        op.add_column('interviews', sa.Column('tts_source', sa.String(length=10), nullable=True,
                                              server_default='provider'))


def downgrade():
    op.drop_column('interviews', 'tts_source')
