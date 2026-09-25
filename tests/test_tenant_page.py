"""Organization page: groups, admins, content and quotas in one place."""
import pytest

from app import db


def tid(world, name):
    return world[name].get_url_identifier()


@pytest.mark.parametrize('actor', ['root', 'dir_a'])
def test_tenant_page_renders(world, content, login, actor):
    html = login(world[actor]).get(f"/admin/tenants/{tid(world, 'lycee_a')}").get_data(as_text=True)
    assert '3A' in html and '3B' in html and 'CODE3A' in html  # groups tab
    assert 'dir_a@test.local' in html                         # admins tab
    assert 'Quiz Alpha' in html and 'Interview Alpha' in html  # content tab
    assert 'Quiz Bravo' not in html and '2C' not in html        # nothing from lycee_b


def test_tenant_page_forbidden_outside_scope(world, login):
    assert login(world['dir_b']).get(f"/admin/tenants/{tid(world, 'lycee_a')}").status_code == 302
    assert login(world['prof_3a']).get(f"/admin/tenants/{tid(world, 'lycee_a')}").status_code == 302


def test_admin_tools_only_for_superadmin(world, login):
    url = f"/admin/tenants/{tid(world, 'lycee_a')}"
    assert 'id="add-admin-form"' in login(world['root']).get(url).get_data(as_text=True)
    assert 'id="add-admin-form"' not in login(world['dir_a']).get(url).get_data(as_text=True)


@pytest.mark.parametrize('old, anchor', [('admins', '#admins'), ('groups', '#groups'), ('quizzes', '#content')])
def test_former_subpages_redirect_to_tabs(world, login, old, anchor):
    resp = login(world['dir_a']).get(f"/admin/tenants/{tid(world, 'lycee_a')}/{old}")
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(f"/admin/tenants/{tid(world, 'lycee_a')}{anchor}")


def test_former_group_form_opens_group_form_with_tenant(world, login):
    resp = login(world['dir_a']).get(f"/admin/tenants/{tid(world, 'lycee_a')}/groups/create")
    assert resp.headers['Location'].endswith(f"/admin/group/create?tenant={tid(world, 'lycee_a')}")
    html = login(world['root']).get(resp.headers['Location']).get_data(as_text=True)
    assert f'<option value="{world["lycee_a"].id}" selected>' in html


def test_admin_candidates(world, login):
    url = f"/admin/tenants/{tid(world, 'lycee_a')}/admins/candidates?q="
    found = {u['username'] for u in login(world['root']).get(url + 'dir').get_json()}
    assert found == {'dir_b'}  # dir_a already admin
    assert login(world['root']).get(url + 'root').get_json() == []  # superadmins see everything already
    # Organization admins can't appoint admins
    assert login(world['dir_a']).get(url + 'dir').status_code == 302


def test_add_and_remove_admin(world, login):
    tenant, prof = world['lycee_a'], world['prof_3a']
    client = login(world['root'])
    resp = client.post(f"/admin/tenants/{tid(world, 'lycee_a')}/admins/add", data={'user': prof.get_url_identifier()})
    assert resp.headers['Location'].endswith('#admins')
    assert tenant.is_admin(prof)
    client.post(f"/admin/tenants/{tid(world, 'lycee_a')}/admins/{prof.get_url_identifier()}/remove")
    assert not tenant.is_admin(prof)


def test_organization_admin_cannot_add_admin(world, login):
    login(world['dir_a']).post(f"/admin/tenants/{tid(world, 'lycee_a')}/admins/add",
                               data={'user': world['prof_3a'].get_url_identifier()})
    assert not world['lycee_a'].is_admin(world['prof_3a'])


def test_list_goes_straight_to_single_tenant(world, login):
    resp = login(world['dir_a']).get('/admin/tenants/list')
    assert resp.headers['Location'].endswith(f"/admin/tenants/{tid(world, 'lycee_a')}")
    world['lycee_b'].add_admin(world['dir_a'])
    db.session.commit()
    html = login(world['dir_a']).get('/admin/tenants/list').get_data(as_text=True)
    assert 'Lycee A' in html and 'Lycee B' in html


def test_group_creation_lands_on_group_page(world, login):
    resp = login(world['dir_a']).post('/admin/group/create', data={'name': 'Nouveau', 'tenant_id': world['lycee_a'].id})
    assert '/admin/group/' in resp.headers['Location'] and not resp.headers['Location'].endswith('/groups')
