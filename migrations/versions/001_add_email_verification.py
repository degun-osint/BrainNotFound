"""Add email verification and password reset fields

Revision ID: 001_email_verification
Revises:
Create Date: 2026-01-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '001_email_verification'
down_revision = None
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add email verification and password reset columns to users table
    # Check if columns already exist to make migration idempotent
    columns_to_add = [
        ('email_verified', sa.Column('email_verified', sa.Boolean(), nullable=True, default=True)),
        ('verification_token', sa.Column('verification_token', sa.String(length=100), nullable=True)),
        ('verification_token_expires', sa.Column('verification_token_expires', sa.DateTime(), nullable=True)),
        ('reset_token', sa.Column('reset_token', sa.String(length=100), nullable=True)),
        ('reset_token_expires', sa.Column('reset_token_expires', sa.DateTime(), nullable=True)),
    ]

    with op.batch_alter_table('users', schema=None) as batch_op:
        for col_name, col_def in columns_to_add:
            if not column_exists('users', col_name):
                batch_op.add_column(col_def)

    # Create unique constraints if columns were added
    # Note: constraints may already exist, so we handle errors gracefully
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_constraints = [c['name'] for c in inspector.get_unique_constraints('users')]

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'uq_users_verification_token' not in existing_constraints:
            try:
                batch_op.create_unique_constraint('uq_users_verification_token', ['verification_token'])
            except Exception:
                pass
        if 'uq_users_reset_token' not in existing_constraints:
            try:
                batch_op.create_unique_constraint('uq_users_reset_token', ['reset_token'])
            except Exception:
                pass

    # Set existing users as verified
    op.execute("UPDATE users SET email_verified = 1 WHERE email_verified IS NULL")


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_reset_token', type_='unique')
        batch_op.drop_constraint('uq_users_verification_token', type_='unique')
        batch_op.drop_column('reset_token_expires')
        batch_op.drop_column('reset_token')
        batch_op.drop_column('verification_token_expires')
        batch_op.drop_column('verification_token')
        batch_op.drop_column('email_verified')
