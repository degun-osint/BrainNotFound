"""Role matrix for user/group administration (superadmin > tenant > group > user)."""
import pytest

from app import db
from app.models import Group, User, user_groups


def reload(user):
    return db.session.get(User, user.id)


def role_in(user, group):
    return db.session.execute(
        user_groups.select().where(
            user_groups.c.user_id == user.id,
            user_groups.c.group_id == group.id,
        )
    ).first()


# ==================== can_manage_user (model) ====================

@pytest.mark.parametrize('actor, target, expected', [
    # Superadmin manages everyone but themselves
    ('root', 'dir_a', True),
    ('root', 'eleve_ab', True),
    ('root', 'root', False),
    # Tenant admin: users and group admins fully inside their tenant
    ('dir_a', 'prof_3a', True),
    ('dir_a', 'eleve_3a_3b', True),
    ('dir_a', 'eleve_ab', False),   # also in lycee_b
    ('dir_a', 'dir_b', False),      # peer
    ('dir_a', 'root', False),       # superior
    ('dir_b', 'eleve_3a', False),   # other tenant
    # Group admin: plain users fully inside their groups
    ('prof_3a', 'eleve_3a', True),
    ('prof_3a', 'eleve_3a_3b', False),  # also in another teacher's class
    ('prof_3a', 'eleve_ab', False),
    ('prof_3a', 'prof_3b', False),
    ('prof_3a', 'dir_a', False),
])
def test_can_manage_user(world, actor, target, expected):
    assert world[actor].can_manage_user(world[target]) is expected


def test_can_manage_user_rejects_group_admin_shared_with_peer(world):
    # prof_3b also sits in 3A as a member: prof_3a still can't touch a peer
    world['prof_3b'].add_to_group(world['g3a'], 'member')
    db.session.commit()
    assert not world['prof_3a'].can_manage_user(world['prof_3b'])


def test_can_access_user_stays_permissive_for_reading(world):
    # Read access (grades) only needs one shared group
    assert world['prof_3a'].can_access_user(world['eleve_ab'])
    assert world['dir_a'].can_access_user(world['eleve_ab'])


# ==================== edit_user ====================

def test_group_admin_cannot_reset_peer_password(world, login):
    client = login(world['prof_3a'])
    world['prof_3b'].add_to_group(world['g3a'], 'member')
    db.session.commit()
    uid = world['prof_3b'].get_url_identifier()

    client.post(f'/admin/user/{uid}/edit', data={
        'username': 'prof_3b', 'email': 'prof_3b@test.local', 'password': 'hacked',
    })

    assert reload(world['prof_3b']).check_password('password')


def test_tenant_admin_cannot_edit_user_shared_with_other_tenant(world, login):
    client = login(world['dir_b'])
    uid = world['eleve_ab'].get_url_identifier()

    client.post(f'/admin/user/{uid}/edit', data={
        'username': 'eleve_ab', 'email': 'pwned@evil.test', 'password': 'hacked',
    })

    user = reload(world['eleve_ab'])
    assert user.email == 'eleve_ab@test.local'
    assert user.check_password('password')


def test_group_admin_can_edit_own_student(world, login):
    client = login(world['prof_3a'])
    uid = world['eleve_3a'].get_url_identifier()

    client.post(f'/admin/user/{uid}/edit', data={
        'username': 'eleve_3a', 'email': 'eleve_3a@test.local', 'password': 'newpass',
        'group_ids': [str(world['g3a'].id)],
    })

    assert reload(world['eleve_3a']).check_password('newpass')


# ==================== delete_user / bulk_delete ====================

def test_tenant_admin_cannot_delete_user_shared_with_other_tenant(world, login):
    client = login(world['dir_b'])
    client.post(f"/admin/user/{world['eleve_ab'].get_url_identifier()}/delete")
    assert reload(world['eleve_ab']) is not None


def test_tenant_admin_can_delete_group_admin_of_own_tenant(world, login):
    client = login(world['dir_a'])
    client.post(f"/admin/user/{world['prof_3b'].get_url_identifier()}/delete")
    assert reload(world['prof_3b']) is None


def test_bulk_delete_skips_unmanageable_users(world, login):
    client = login(world['prof_3a'])
    ids = [world[n].id for n in ('eleve_3a', 'eleve_3a_3b', 'prof_3b', 'root')]

    client.post('/admin/users/bulk-delete', data={'user_ids': ids})

    assert reload(world['eleve_3a']) is None
    for name in ('eleve_3a_3b', 'prof_3b', 'root'):
        assert reload(world[name]) is not None


# ==================== bulk_change_group ====================

def test_bulk_replace_keeps_groups_outside_admin_scope(world, login):
    client = login(world['dir_a'])
    student = world['eleve_ab']

    client.post('/admin/users/bulk-change-group', data={
        'user_ids': [student.id], 'action': 'replace', 'group_id': world['g3b'].id,
    })

    group_ids = {g.id for g in reload(student).groups}
    assert group_ids == {world['g3b'].id, world['g2c'].id}


def test_bulk_change_group_cannot_touch_peer_admin(world, login):
    world['prof_3b'].add_to_group(world['g3a'], 'member')
    db.session.commit()
    client = login(world['prof_3a'])

    client.post('/admin/users/bulk-change-group', data={
        'user_ids': [world['prof_3b'].id], 'action': 'remove', 'group_id': world['g3a'].id,
    })

    assert role_in(world['prof_3b'], world['g3a']) is not None


def test_bulk_add_uses_member_role(world, login):
    client = login(world['dir_a'])

    client.post('/admin/users/bulk-change-group', data={
        'user_ids': [world['eleve_3a'].id], 'action': 'add', 'group_id': world['g3b'].id,
    })

    assert role_in(world['eleve_3a'], world['g3b']).role == 'member'


# ==================== edit_group ====================

def test_tenant_admin_cannot_move_group_to_foreign_tenant(world, login):
    client = login(world['dir_a'])

    client.post(f"/admin/group/{world['g3a'].get_url_identifier()}/edit", data={
        'name': '3A', 'tenant_id': world['lycee_b'].id,
    })

    assert db.session.get(Group, world['g3a'].id).tenant_id == world['lycee_a'].id


def test_group_admin_cannot_move_group(world, login):
    client = login(world['prof_3a'])

    client.post(f"/admin/group/{world['g3a'].get_url_identifier()}/edit", data={
        'name': '3A', 'tenant_id': world['lycee_b'].id,
    })

    assert db.session.get(Group, world['g3a'].id).tenant_id == world['lycee_a'].id


def test_edit_group_rejects_empty_name(world, login):
    client = login(world['dir_a'])

    resp = client.post(f"/admin/group/{world['g3a'].get_url_identifier()}/edit", data={'name': ''})

    assert resp.status_code == 200
    assert db.session.get(Group, world['g3a'].id).name == '3A'


def test_superadmin_can_move_group(world, login):
    client = login(world['root'])

    client.post(f"/admin/group/{world['g3a'].get_url_identifier()}/edit", data={
        'name': '3A', 'tenant_id': world['lycee_b'].id,
    })

    assert db.session.get(Group, world['g3a'].id).tenant_id == world['lycee_b'].id


# ==================== users list ====================

def test_tenant_admin_user_list_hides_superadmins(world, login):
    client = login(world['dir_a'])

    html = client.get('/admin/users').get_data(as_text=True)

    assert 'root@test.local' not in html
    assert 'eleve_3a@test.local' in html
    assert 'eleve_2c' not in html


# ==================== smoke: admin pages render for every role ====================

@pytest.mark.parametrize('actor', ['root', 'dir_a', 'prof_3a'])
@pytest.mark.parametrize('path', [
    '/admin/dashboard',
    '/admin/quizzes',
    '/admin/users',
    '/admin/groups',
    '/admin/group/{g3a}/edit',
    '/admin/group/{g3a}/users',
    '/admin/user/{eleve_3a}/edit',
    '/admin/user/{eleve_3a}/grades',
])
def test_admin_pages_render(world, login, actor, path):
    client = login(world[actor])
    url = path.format(g3a=world['g3a'].get_url_identifier(),
                      eleve_3a=world['eleve_3a'].get_url_identifier())

    resp = client.get(url)

    assert resp.status_code == 200, resp.status_code


# ==================== query budget (N+1 regressions) ====================

def test_users_page_query_count_does_not_grow_with_rows(app, world, login):
    from sqlalchemy import event
    from tests.conftest import make_user
    from app import db as _db

    def count_queries(client):
        counter = []
        listener = lambda *a, **k: counter.append(1)  # noqa: E731
        event.listen(_db.engine, 'before_cursor_execute', listener)
        client.get('/admin/users')
        event.remove(_db.engine, 'before_cursor_execute', listener)
        return len(counter)

    client = login(world['dir_a'])
    baseline = count_queries(client)
    for i in range(10):
        make_user(f'extra_{i}', groups=[world['g3a'], world['g3b']])
    assert count_queries(client) <= baseline + 2
