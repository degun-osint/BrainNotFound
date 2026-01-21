"""Add login tracking fields

Revision ID: 002_login_tracking
Revises: 001_email_verification
Create Date: 2026-01-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '002_login_tracking'
down_revision = '001_email_verification'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add login tracking columns to users table
    # Check if columns already exist to make migration idempotent
    with op.batch_alter_table('users', schema=None) as batch_op:
        if not column_exists('users', 'last_login'):
            batch_op.add_column(sa.Column('last_login', sa.DateTime(), nullable=True))
        if not column_exists('users', 'last_login_ip'):
            batch_op.add_column(sa.Column('last_login_ip', sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_login_ip')
        batch_op.drop_column('last_login')
