"""Admin scope helpers and content access (quizzes, interviews)."""
import pytest
from flask_login import login_user

from app import db
from app.models import Interview, Quiz, QuizResponse
from app.utils import scope


@pytest.fixture
def as_user(app):
    """Run scope helpers inside a request as a given user (optionally with a navbar tenant)."""
    def _as(user, tenant=None):
        ctx = app.test_request_context()
        ctx.push()
        login_user(user)
        if tenant:
            scope.set_tenant_context(tenant)
        return ctx
    return _as


def titles(query):
    return {item.title for item in query}


# ==================== scoped lists ====================

@pytest.mark.parametrize('actor, expected', [
    ('root', {'Quiz Alpha', 'Quiz Bravo', 'Quiz Shared', 'Quiz Draft'}),
    ('dir_a', {'Quiz Alpha', 'Quiz Shared'}),
    ('dir_b', {'Quiz Bravo', 'Quiz Shared'}),
    ('prof_3a', {'Quiz Alpha', 'Quiz Shared', 'Quiz Draft'}),
    ('prof_3b', set()),
])
def test_scoped_quizzes(world, content, as_user, actor, expected):
    ctx = as_user(world[actor])
    assert titles(scope.scoped_quizzes()) == expected
    ctx.pop()


def test_tenant_context_narrows_superadmin_scope(world, content, as_user):
    ctx = as_user(world['root'], tenant=world['lycee_b'])
    assert titles(scope.scoped_quizzes()) == {'Quiz Bravo', 'Quiz Shared'}
    assert {g.name for g in scope.scoped_groups()} == {'2C'}
    ctx.pop()


def test_stale_tenant_context_is_ignored(world, content, as_user):
    # dir_a somehow has lycee_b in session (e.g. rights removed since): ignored
    ctx = as_user(world['dir_a'], tenant=world['lycee_b'])
    assert scope.get_tenant_context() is None
    assert titles(scope.scoped_quizzes()) == {'Quiz Alpha', 'Quiz Shared'}
    ctx.pop()


@pytest.mark.parametrize('actor, expected', [
    ('dir_a', {'dir_a', 'prof_3a', 'prof_3b', 'eleve_3a', 'eleve_3a_3b', 'eleve_ab'}),
    ('prof_3a', {'prof_3a', 'eleve_3a', 'eleve_3a_3b', 'eleve_ab'}),
    ('dir_b', {'dir_b', 'eleve_ab'}),
])
def test_scoped_users_never_include_superadmins(world, as_user, actor, expected):
    ctx = as_user(world[actor])
    assert {u.username for u in scope.scoped_users()} == expected
    ctx.pop()


def test_validate_group_ids_drops_foreign_and_junk(world, as_user):
    ctx = as_user(world['dir_a'])
    groups = scope.validate_group_ids([world['g3a'].id, str(world['g2c'].id), 'x', ''])
    assert [g.name for g in groups] == ['3A']
    ctx.pop()


def test_assign_groups_keeps_groups_outside_scope(world, content, as_user):
    quiz = content['quiz_shared']
    ctx = as_user(world['dir_b'])
    scope.assign_groups(quiz.groups, [])  # dir_b unassigns everything they can see
    db.session.commit()
    ctx.pop()
    assert {g.name for g in db.session.get(Quiz, quiz.id).groups} == {'3A'}


# ==================== pages ====================

def test_quiz_list_for_tenant_admin_without_context(world, content, login):
    # Regression: used to fall back to the group-admin branch and show nothing
    html = login(world['dir_a']).get('/admin/quizzes').get_data(as_text=True)
    assert 'Quiz Alpha' in html and 'Quiz Shared' in html
    assert 'Quiz Bravo' not in html


def test_quiz_results_group_filter_is_scoped(world, content, login):
    shared = content['quiz_shared']
    for student in ('eleve_3a', 'eleve_ab'):
        db.session.add(QuizResponse(user_id=world[student].id, quiz_id=shared.id))
    # A learner only in lycee_b answering the shared quiz
    from tests.conftest import make_user
    outsider = make_user('eleve_2c_only', groups=[world['g2c']])
    db.session.add(QuizResponse(user_id=outsider.id, quiz_id=shared.id))
    db.session.commit()

    client = login(world['prof_3a'])
    url = f"/admin/quiz/{shared.get_url_identifier()}/results"
    assert 'eleve_2c_only' not in client.get(url).get_data(as_text=True)
    assert 'eleve_2c_only' not in client.get(f"{url}?group={world['g2c'].id}").get_data(as_text=True)


# ==================== interviews (IDOR) ====================

@pytest.mark.parametrize('suffix', ['', '/edit', '/export', '/export-json'])
def test_foreign_interview_pages_are_blocked(world, content, login, suffix):
    client = login(world['prof_3a'])
    resp = client.get(f"/interview/admin/interviews/{content['itw_b'].get_url_identifier()}{suffix}")
    assert resp.status_code == 302


def test_foreign_interview_cannot_be_deleted(world, content, login):
    client = login(world['dir_a'])
    client.post(f"/interview/admin/interviews/{content['itw_b'].get_url_identifier()}/delete")
    assert db.session.get(Interview, content['itw_b'].id) is not None


def test_own_interview_is_accessible(world, content, login):
    client = login(world['prof_3a'])
    resp = client.get(f"/interview/admin/interviews/{content['itw_a'].get_url_identifier()}")
    assert resp.status_code == 200


def test_interview_list_is_scoped(world, content, login):
    html = login(world['dir_b']).get('/interview/admin/interviews').get_data(as_text=True)
    assert 'Interview Bravo' in html
    assert 'Interview Alpha' not in html
