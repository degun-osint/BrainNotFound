"""Add multi-tenant support with tenants table and FK relationships.

Revision ID: 007_tenants
Revises: 006_group_max_members
Create Date: 2026-01-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_tenants'
down_revision = '006_group_max_members'
branch_labels = None
depends_on = None


def upgrade():
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('max_users', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_quizzes', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_groups', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_storage_mb', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('contact_email', sa.String(200), nullable=True),
        sa.Column('contact_name', sa.String(200), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # Create tenant_admins association table
    op.create_table(
        'tenant_admins',
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('tenant_id', 'user_id')
    )

    # Add tenant_id to groups table
    op.add_column('groups', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.create_index('ix_groups_tenant_id', 'groups', ['tenant_id'])
    op.create_foreign_key('fk_groups_tenant_id', 'groups', 'tenants', ['tenant_id'], ['id'])

    # Add tenant_id to quizzes table
    op.add_column('quizzes', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.create_index('ix_quizzes_tenant_id', 'quizzes', ['tenant_id'])
    op.create_foreign_key('fk_quizzes_tenant_id', 'quizzes', 'tenants', ['tenant_id'], ['id'])


def downgrade():
    # Remove tenant_id from quizzes
    op.drop_constraint('fk_quizzes_tenant_id', 'quizzes', type_='foreignkey')
    op.drop_index('ix_quizzes_tenant_id', table_name='quizzes')
    op.drop_column('quizzes', 'tenant_id')

    # Remove tenant_id from groups
    op.drop_constraint('fk_groups_tenant_id', 'groups', type_='foreignkey')
    op.drop_index('ix_groups_tenant_id', table_name='groups')
    op.drop_column('groups', 'tenant_id')

    # Drop tenant_admins table
    op.drop_table('tenant_admins')

    # Drop tenants table
    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.drop_table('tenants')
