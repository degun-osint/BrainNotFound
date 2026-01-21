"""Add site settings table for backup and branding configuration.

Revision ID: 004_site_settings
Revises: 003_exam_mode
Create Date: 2025-01-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_site_settings'
down_revision = '003_exam_mode'
branch_labels = None
depends_on = None


def upgrade():
    # Create site_settings table
    op.create_table('site_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        # Site branding
        sa.Column('site_title', sa.String(100), nullable=True, server_default='BrainNotFound'),
        sa.Column('contact_email', sa.String(255), nullable=True, server_default='thebot@brainnotfound.app'),
        # FTP Backup settings
        sa.Column('ftp_enabled', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('ftp_host', sa.String(255), nullable=True),
        sa.Column('ftp_port', sa.Integer(), nullable=True, server_default='21'),
        sa.Column('ftp_username', sa.String(255), nullable=True),
        sa.Column('ftp_password_encrypted', sa.Text(), nullable=True),
        sa.Column('ftp_path', sa.String(500), nullable=True, server_default='/backups'),
        sa.Column('ftp_use_tls', sa.Boolean(), nullable=True, server_default='1'),
        # Backup schedule
        sa.Column('backup_frequency', sa.String(20), nullable=True, server_default='daily'),
        sa.Column('backup_hour', sa.Integer(), nullable=True, server_default='3'),
        sa.Column('backup_day', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('backup_retention_days', sa.Integer(), nullable=True, server_default='30'),
        # Last backup info
        sa.Column('last_backup_at', sa.DateTime(), nullable=True),
        sa.Column('last_backup_status', sa.String(20), nullable=True),
        sa.Column('last_backup_message', sa.Text(), nullable=True),
        sa.Column('last_backup_size', sa.BigInteger(), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Insert default settings row
    op.execute(
        "INSERT INTO site_settings (site_title, contact_email, ftp_enabled) "
        "VALUES ('BrainNotFound', 'thebot@brainnotfound.app', 0)"
    )


def downgrade():
    op.drop_table('site_settings')
