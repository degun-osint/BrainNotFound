"""Admin lists: status and search filters, and the navbar organization context."""
import pytest

from app import db


def titles(html, candidates):
    return {t for t in candidates if t in html}


QUIZZES = ('Quiz Alpha', 'Quiz Bravo', 'Quiz Shared', 'Quiz Draft')


@pytest.mark.parametrize('status, expected', [
    ('', set(QUIZZES)),
    ('inactive', {'Quiz Alpha'}),
    ('active', {'Quiz Bravo', 'Quiz Shared', 'Quiz Draft'}),
    ('no_group', {'Quiz Draft'}),
])
def test_quiz_status_filter(world, content, login, status, expected):
    content['quiz_a'].is_active = False
    db.session.commit()
    html = login(world['root']).get(f'/admin/quizzes?status={status}').get_data(as_text=True)
    assert titles(html, QUIZZES) == expected


def test_interview_status_filter(world, content, login):
    content['itw_b'].is_active = False
    db.session.commit()
    html = login(world['root']).get('/interview/admin/interviews?status=inactive').get_data(as_text=True)
    assert 'Interview Bravo' in html and 'Interview Alpha' not in html


def test_status_kept_in_pagination_links(world, content, login):
    from app.models import Quiz
    for i in range(25):
        db.session.add(Quiz(title=f'Bulk {i}', markdown_content='# x', tenant_id=world['lycee_a'].id))
    db.session.commit()
    html = login(world['root']).get('/admin/quizzes?status=active').get_data(as_text=True)
    assert 'status=active' in html and 'page=2' in html


def test_groups_search_and_status(world, login):
    world['g3b'].is_active = False
    db.session.commit()
    client = login(world['dir_a'])
    html = client.get('/admin/groups?search=3A').get_data(as_text=True)
    assert 'CODE3A' in html and 'CODE3B' not in html
    html = client.get('/admin/groups?status=inactive').get_data(as_text=True)
    assert 'CODE3B' in html and 'CODE3A' not in html
    html = client.get('/admin/groups').get_data(as_text=True)
    assert 'CODE2C' not in html  # other organization


def test_organization_context_narrows_every_list(world, content, login):
    client = login(world['root'])
    client.get(f"/admin/set-tenant-context/{world['lycee_b'].get_url_identifier()}")
    groups = client.get('/admin/groups').get_data(as_text=True)
    assert 'CODE2C' in groups and 'CODE3A' not in groups
    assert 'Lycee B' in groups  # "Organization: Lycee B" reminder above the list
    quizzes = client.get('/admin/quizzes').get_data(as_text=True)
    assert 'Quiz Bravo' in quizzes and 'Quiz Alpha' not in quizzes
    interviews = client.get('/interview/admin/interviews').get_data(as_text=True)
    assert 'Interview Bravo' in interviews and 'Interview Alpha' not in interviews
    users = client.get('/admin/users').get_data(as_text=True)
    assert 'eleve_ab' in users and 'eleve_3a_3b' not in users


def test_users_filters_keep_sort(world, login):
    html = login(world['root']).get('/admin/users?sort=username&dir=asc&role=user').get_data(as_text=True)
    assert 'name="sort" value="username"' in html and 'name="dir" value="asc"' in html
