"""Create/edit user forms: global role, role per group, invitation instead of password."""
import pytest

from app import db
from app.models import User, user_groups


def role(user, group):
    row = db.session.execute(user_groups.select().where(
        user_groups.c.user_id == user.id, user_groups.c.group_id == group.id)).first()
    return row.role if row else None


def edit(client, user, **fields):
    data = {'username': user.username, 'email': user.email}
    data.update(fields)
    return client.post(f'/admin/user/{user.get_url_identifier()}/edit', data=data)


@pytest.mark.parametrize('actor', ['root', 'dir_a', 'prof_3a'])
def test_forms_render(world, login, actor):
    client = login(world[actor])
    assert client.get('/admin/user/create').status_code == 200
    html = client.get(f"/admin/user/{world['eleve_3a'].get_url_identifier()}").get_data(as_text=True)
    assert 'data-panel="edit"' in html


def test_organization_admin_sets_roles_group_by_group(world, login):
    student, g3a, g3b = world['eleve_3a'], world['g3a'], world['g3b']
    edit(login(world['dir_a']), student, group_role_seen=[g3a.id, g3b.id],
         **{f'group_role_{g3a.id}': 'admin', f'group_role_{g3b.id}': 'member'})
    assert (role(student, g3a), role(student, g3b)) == ('admin', 'member')


def test_instructor_cannot_name_instructors(world, login):
    student, g3a = world['eleve_3a'], world['g3a']
    edit(login(world['prof_3a']), student, group_role_seen=[g3a.id], **{f'group_role_{g3a.id}': 'admin'})
    assert role(student, g3a) == 'member'


def test_groups_not_displayed_or_out_of_scope_are_untouched(world, login):
    student, g3a, g3b = world['eleve_3a_3b'], world['g3a'], world['g3b']
    # dir_a manages everything; form only shows 3A: 3B membership must stay
    edit(login(world['dir_a']), student, group_role_seen=[g3a.id], **{f'group_role_{g3a.id}': ''})
    assert role(student, g3a) is None and role(student, g3b) == 'member'


def test_forged_out_of_scope_group_is_ignored(world, login):
    student, g2c = world['eleve_3a'], world['g2c']
    edit(login(world['prof_3a']), student, group_role_seen=[g2c.id], **{f'group_role_{g2c.id}': 'member'})
    assert role(student, g2c) is None


def test_superadmin_makes_organization_admin(world, login):
    student = world['eleve_3a']
    edit(login(world['root']), student, global_role='tenant_admin', tenant_ids=[world['lycee_a'].id])
    assert db.session.get(User, student.id).admin_tenant_ids() == {world['lycee_a'].id}


def test_non_superadmin_cannot_change_global_role(world, login):
    student = world['eleve_3a']
    edit(login(world['dir_a']), student, global_role='superadmin')
    assert not db.session.get(User, student.id).is_admin


def test_create_without_password_sends_invitation(world, login, monkeypatch):
    from app.utils import email_sender
    sent = []
    monkeypatch.setattr(email_sender, 'send_email_async', lambda msg: sent.append(msg))
    g3a = world['g3a']

    resp = login(world['prof_3a']).post(f'/admin/user/create?group={g3a.id}', data={
        'username': 'invited', 'email': 'invited@test.local',
        'group_role_seen': [g3a.id], f'group_role_{g3a.id}': 'member'})

    user = User.query.filter_by(username='invited').first()
    assert role(user, g3a) == 'member' and user.reset_token
    assert sent and sent[0].recipients == ['invited@test.local']
    assert resp.headers['Location'].endswith(f'/admin/group/{g3a.get_url_identifier()}')


def test_create_requires_a_group_in_scope(world, login):
    g3b = world['g3b']
    login(world['prof_3a']).post('/admin/user/create', data={
        'username': 'sneaky', 'email': 'sneaky@test.local', 'password': 'x',
        'group_role_seen': [g3b.id], f'group_role_{g3b.id}': 'member'})
    assert User.query.filter_by(username='sneaky').first() is None
