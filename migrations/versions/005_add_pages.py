"""Add pages table for custom content pages.

Revision ID: 005_pages
Revises: 004_site_settings
Create Date: 2025-01-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_pages'
down_revision = '004_site_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Create pages table
    op.create_table('pages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        # Display location: 'menu', 'footer', 'both', 'none'
        sa.Column('location', sa.String(20), nullable=True, server_default='footer'),
        sa.Column('display_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('is_published', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('open_new_tab', sa.Boolean(), nullable=True, server_default='0'),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Create index for faster lookups
    op.create_index('ix_pages_slug', 'pages', ['slug'], unique=True)
    op.create_index('ix_pages_location', 'pages', ['location'])


def downgrade():
    op.drop_index('ix_pages_location', table_name='pages')
    op.drop_index('ix_pages_slug', table_name='pages')
    op.drop_table('pages')
