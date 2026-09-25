"""Navigation: breadcrumb above detail pages, account menu, favicon."""
import re

from app import db


def trail(html):
    """Labels of the breadcrumb, in order ('' when there is none)."""
    match = re.search(r'<nav class="breadcrumb"[^>]*>(.*?)</nav>', html, re.S)
    if not match:
        return []
    return [t.strip() for t in re.findall(r'>([^<>›]+)<', match.group(1)) if t.strip()]


def test_group_page_trail(world, login):
    html = login(world['root']).get(f"/admin/group/{world['g3a'].get_url_identifier()}").get_data(as_text=True)
    assert trail(html) == ['Etablissements', 'Lycee A', '3A']
    assert f"/admin/tenants/{world['lycee_a'].get_url_identifier()}\"" in html


def test_instructor_trail_has_no_organization_link(world, login):
    html = login(world['prof_3a']).get(f"/admin/group/{world['g3a'].get_url_identifier()}").get_data(as_text=True)
    assert trail(html) == ['Lycee A', '3A']
    assert f"/admin/tenants/{world['lycee_a'].get_url_identifier()}\"" not in html


def test_single_organization_admin_sees_no_trail_on_its_page(world, login):
    html = login(world['dir_a']).get(f"/admin/tenants/{world['lycee_a'].get_url_identifier()}").get_data(as_text=True)
    assert trail(html) == []


def test_person_trail(world, login):
    client = login(world['dir_a'])
    one_group = client.get(f"/admin/user/{world['eleve_3a'].get_url_identifier()}").get_data(as_text=True)
    assert trail(one_group)[-2:] == ['3A', 'eleve_3a']
    two_groups = client.get(f"/admin/user/{world['eleve_3a_3b'].get_url_identifier()}").get_data(as_text=True)
    assert trail(two_groups) == ['Utilisateurs', 'eleve_3a_3b']


def test_account_menu(world, login):
    html = login(world['dir_a']).get('/admin/groups').get_data(as_text=True)
    menu = html.split('nav-account', 1)[1].split('</nav>', 1)[0]
    assert '/logout' in menu and '/profile' in menu and '/set-language/en' in menu
    assert '/admin/settings' not in menu  # superadmins only
    assert '/admin/settings' in login(world['root']).get('/admin/groups').get_data(as_text=True)


def test_favicon(client):
    resp = client.get('/favicon.ico')
    assert resp.status_code == 301 and resp.headers['Location'].endswith('/static/img/favicon.svg')
    assert client.get('/static/img/favicon.svg').status_code == 200


def test_organization_selector_on_every_admin_page(world, content, login):
    client = login(world['dir_a'])
    world['lycee_b'].add_admin(world['dir_a'])
    db.session.commit()
    for url in ('/admin/groups', f"/admin/tenants/{world['lycee_a'].get_url_identifier()}",
                '/interview/admin/interviews'):
        assert 'tenant-dropdown' in client.get(url).get_data(as_text=True), url
