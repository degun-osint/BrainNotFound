"""Person page: roles, groups, results and the edit form in one place."""
import pytest

from app import db
from app.models import QuizResponse


def uid(world, name):
    return world[name].get_url_identifier()


def test_person_page_shows_groups_and_results_in_scope(world, content, login):
    for quiz in ('quiz_a', 'quiz_b'):
        db.session.add(QuizResponse(user_id=world['eleve_ab'].id, quiz_id=content[quiz].id,
                                    total_score=5, max_score=10))
    db.session.commit()
    html = login(world['dir_a']).get(f"/admin/user/{uid(world, 'eleve_ab')}").get_data(as_text=True)
    assert '3A' in html and '2C' in html            # every group of the person is listed
    assert 'Quiz Alpha' in html                      # result in dir_a's organization
    assert 'Quiz Bravo' not in html                  # result in the other organization


@pytest.mark.parametrize('actor, target, editable, deletable', [
    ('root', 'dir_a', True, True),
    ('dir_a', 'prof_3a', True, True),
    ('prof_3a', 'eleve_3a', True, True),
    ('prof_3a', 'eleve_3a_3b', True, False),  # also in 3B: editable, but only deletable by who manages 3B too
    ('prof_3a', 'eleve_ab', False, False),    # also in another organization
])
def test_edit_and_delete_only_when_allowed(world, login, actor, target, editable, deletable):
    resp = login(world[actor]).get(f"/admin/user/{uid(world, target)}")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert ('data-panel="edit"' in html) is editable
    assert (f"/admin/user/{uid(world, target)}/delete" in html) is deletable


def test_person_page_forbidden_outside_scope(world, login):
    assert login(world['dir_b']).get(f"/admin/user/{uid(world, 'eleve_3a')}").status_code == 302


def test_own_page_is_read_only(world, login):
    html = login(world['dir_a']).get(f"/admin/user/{uid(world, 'dir_a')}").get_data(as_text=True)
    assert 'data-panel="edit"' not in html and 'Lycee A' in html


def test_former_urls_redirect_to_tabs(world, login):
    client = login(world['dir_a'])
    resp = client.get(f"/admin/user/{uid(world, 'eleve_3a')}/grades")
    assert resp.status_code == 301 and resp.headers['Location'].endswith(f"/admin/user/{uid(world, 'eleve_3a')}#results")
    resp = client.get(f"/admin/user/{uid(world, 'eleve_3a')}/edit")
    assert resp.headers['Location'].endswith(f"/admin/user/{uid(world, 'eleve_3a')}#edit")


def test_saving_returns_to_person_page(world, login):
    student = world['eleve_3a']
    resp = login(world['dir_a']).post(f"/admin/user/{student.get_url_identifier()}/edit",
                                      data={'username': student.username, 'email': student.email, 'first_name': 'Zoe'})
    assert resp.headers['Location'].endswith(f"/admin/user/{student.get_url_identifier()}")
    assert student.first_name == 'Zoe'


def test_validation_error_reopens_edit_tab(world, login):
    student = world['eleve_3a']
    resp = login(world['dir_a']).post(f"/admin/user/{student.get_url_identifier()}/edit",
                                      data={'username': 'eleve_ab', 'email': student.email})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'class="tab-btn active" data-tab="edit"' in html
    assert db.session.get(type(student), student.id).username == 'eleve_3a'
