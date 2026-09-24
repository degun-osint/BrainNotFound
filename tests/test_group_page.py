"""Group page: members, per-group roles, join code, password reset links."""
import pytest

from app import db
from app.models import Group, User, user_groups


def role(user, group):
    row = db.session.execute(user_groups.select().where(
        user_groups.c.user_id == user.id, user_groups.c.group_id == group.id)).first()
    return row.role if row else None


def gid(world, name):
    return world[name].get_url_identifier()


@pytest.mark.parametrize('actor', ['root', 'dir_a', 'prof_3a'])
def test_group_page_renders(world, content, login, actor):
    html = login(world[actor]).get(f"/admin/group/{gid(world, 'g3a')}").get_data(as_text=True)
    assert 'eleve_3a' in html and 'Quiz Alpha' in html and 'CODE3A' in html
    assert 'register?code=CODE3A' in html


def test_group_page_forbidden_outside_scope(world, login):
    assert login(world['prof_3a']).get(f"/admin/group/{gid(world, 'g3b')}").status_code == 302
    assert login(world['dir_b']).get(f"/admin/group/{gid(world, 'g3a')}").status_code == 302


def test_old_members_url_redirects(world, login):
    resp = login(world['prof_3a']).get(f"/admin/group/{gid(world, 'g3a')}/users")
    assert resp.status_code == 301 and resp.headers['Location'].endswith(f"/admin/group/{gid(world, 'g3a')}")


def test_candidates_are_scoped_and_exclude_members(world, login):
    found = login(world['dir_a']).get(f"/admin/group/{gid(world, 'g3b')}/candidates?q=eleve").get_json()
    names = {u['username'] for u in found}
    assert names == {'eleve_3a', 'eleve_ab'}  # eleve_3a_3b already in 3B; nobody from lycee_b only


def test_instructor_adds_and_removes_learner(world, login):
    student = User(username='newbie', email='newbie@test.local')
    student.set_password('x')
    db.session.add(student)
    db.session.flush()
    student.add_to_group(world['g3a'])
    db.session.commit()
    client = login(world['dir_a'])

    client.post(f"/admin/group/{gid(world, 'g3b')}/members/add", data={'user': student.get_url_identifier()})
    assert role(student, world['g3b']) == 'member'

    client.post(f"/admin/group/{gid(world, 'g3b')}/members/{student.get_url_identifier()}/remove")
    assert role(student, world['g3b']) is None


def test_instructor_cannot_remove_peer_instructor(world, login):
    world['prof_3b'].add_to_group(world['g3a'], 'admin')
    db.session.commit()
    login(world['prof_3a']).post(f"/admin/group/{gid(world, 'g3a')}/members/{gid(world, 'prof_3b')}/remove")
    assert role(world['prof_3b'], world['g3a']) == 'admin'


def test_only_organization_admins_change_roles(world, login):
    url = f"/admin/group/{gid(world, 'g3a')}/members/{gid(world, 'eleve_3a')}/role"
    login(world['prof_3a']).post(url, data={'role': 'admin'})
    assert role(world['eleve_3a'], world['g3a']) == 'member'

    login(world['dir_a']).post(url, data={'role': 'admin'})
    assert role(world['eleve_3a'], world['g3a']) == 'admin'
    # per group: still a learner in no other group, instructor here only
    assert world['eleve_3a'].is_admin_of_group(world['g3a'].id)


def test_regenerate_join_code(world, login):
    login(world['prof_3a']).post(f"/admin/group/{gid(world, 'g3a')}/regenerate-code")
    assert db.session.get(Group, world['g3a'].id).join_code != 'CODE3A'


def test_invitation_link_prefills_code(client):
    assert 'value="CODE3A"' in client.get('/register?code=CODE3A').get_data(as_text=True)


# ==================== reset links ====================

def test_reset_link_for_manageable_user(world, login):
    data = login(world['prof_3a']).post(f"/admin/user/{gid(world, 'eleve_3a')}/reset-link").get_json()
    user = db.session.get(User, world['eleve_3a'].id)
    assert user.reset_token and data['url'].endswith(user.reset_token) and data['hours'] == 72


def test_reset_link_refused_outside_write_scope(world, login):
    resp = login(world['prof_3a']).post(f"/admin/user/{gid(world, 'eleve_ab')}/reset-link")
    assert resp.status_code == 403
    assert db.session.get(User, world['eleve_ab'].id).reset_token is None


def test_send_reset_email_by_admin(world, login, monkeypatch):
    from app.utils import email_sender
    sent = []
    monkeypatch.setattr(email_sender, 'send_email_async', lambda msg: sent.append(msg))
    login(world['dir_a']).post(f"/admin/user/{gid(world, 'eleve_3a')}/send-reset")
    assert sent and 'administrateur' in sent[0].body and '72 heures' in sent[0].body


# ==================== group <-> organization ====================

def test_single_organization_is_shown_not_hidden(world, login):
    html = login(world['dir_a']).get('/admin/group/create').get_data(as_text=True)
    assert '<select id="tenant_id"' in html and 'Lycee A' in html


def test_group_without_organization_is_refused(world, login):
    login(world['root']).post('/admin/group/create', data={'name': 'Orphan'})
    assert Group.query.filter_by(name='Orphan').first() is None


def test_superadmin_without_any_organization_is_guided(app, login):
    from tests.conftest import make_user
    root = make_user('lonely_root', superadmin=True)
    html = login(root).get('/admin/group/create').get_data(as_text=True)
    assert 'Creer un etablissement' in html and 'disabled' in html


def test_orphan_group_can_be_attached(world, login):
    orphan = Group(name='Legacy', join_code='LEGACY01')
    db.session.add(orphan)
    db.session.commit()
    client = login(world['root'])
    assert 'Sans etablissement' in client.get('/admin/groups').get_data(as_text=True)

    client.post(f'/admin/group/{orphan.get_url_identifier()}/edit',
                data={'name': 'Legacy', 'tenant_id': world['lycee_a'].id})
    assert db.session.get(Group, orphan.id).tenant_id == world['lycee_a'].id


def test_new_learner_and_import_buttons_preselect_the_group(world, login):
    client = login(world['prof_3a'])
    gid_ = world['g3a'].id
    create = client.get(f'/admin/user/create?group={gid_}')
    imp = client.get(f'/admin/users/import?group={gid_}')
    assert create.status_code == 200 and imp.status_code == 200
    assert f'<option value="{gid_}" selected' in imp.get_data(as_text=True)
    assert 'value="member" selected' in create.get_data(as_text=True)
