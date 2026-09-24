"""Drop the legacy users.group_id column (memberships live in user_groups).

Legacy memberships that never made it into user_groups are copied first,
so no one loses access to their group.

Revision ID: 013_drop_user_group_id
Revises: 012_claude_settings
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_drop_user_group_id'
down_revision = '012_claude_settings'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'group_id' not in {c['name'] for c in inspector.get_columns('users')}:
        return

    bind.execute(sa.text("""
        INSERT INTO user_groups (user_id, group_id, role, joined_at)
        SELECT u.id, u.group_id, 'member', u.created_at
        FROM users u
        WHERE u.group_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM `groups` g WHERE g.id = u.group_id)
          AND NOT EXISTS (
              SELECT 1 FROM user_groups ug WHERE ug.user_id = u.id AND ug.group_id = u.group_id
          )
    """))

    for fk in inspector.get_foreign_keys('users'):
        if fk['constrained_columns'] == ['group_id'] and fk.get('name'):
            op.drop_constraint(fk['name'], 'users', type_='foreignkey')
    op.drop_column('users', 'group_id')


def downgrade():
    op.add_column('users', sa.Column('group_id', sa.Integer(), nullable=True))
    op.create_foreign_key('users_group_id_fkey', 'users', 'groups', ['group_id'], ['id'])
