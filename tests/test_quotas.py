"""Tenant limits (users, groups, quizzes, subscription) and monthly AI quotas."""
from datetime import date, timedelta

from app import db
from app.models import Answer, Group, Question, Quiz, QuizResponse, Tenant, User


def reload_tenant(tenant):
    return db.session.get(Tenant, tenant.id)


# ==================== monthly AI counters ====================

def test_increment_is_cumulative_and_limit_enforced(world):
    tenant = world['lycee_a']
    tenant.monthly_ai_corrections = 2
    db.session.commit()

    tenant.increment_ai_corrections()
    tenant.increment_ai_corrections()

    assert reload_tenant(tenant).used_ai_corrections == 2
    assert not tenant.can_use_ai_correction()


def test_counters_reset_on_new_month(world):
    tenant = world['lycee_a']
    tenant.monthly_ai_corrections = 2
    tenant.used_ai_corrections = 2
    tenant.usage_reset_date = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    db.session.commit()

    assert tenant.can_use_ai_correction()
    assert tenant.used_ai_corrections == 0


def test_expired_subscription_blocks_ai(world):
    tenant = world['lycee_a']
    tenant.subscription_expires_at = date.today() - timedelta(days=1)
    db.session.commit()
    assert not tenant.can_use_ai_correction()


def _open_quiz_response(world, quiz, n_answers):
    response = QuizResponse(user_id=world['eleve_3a'].id, quiz_id=quiz.id)
    db.session.add(response)
    db.session.flush()
    answers = []
    for i in range(n_answers):
        q = Question(quiz_id=quiz.id, question_type='open', question_text=f'Q{i}',
                     points=2, expected_answer='42')
        db.session.add(q)
        db.session.flush()
        a = Answer(quiz_response_id=response.id, question_id=q.id, answer_text='42', max_score=2)
        db.session.add(a)
        db.session.flush()
        answers.append({'answer_id': a.id})
    db.session.commit()
    return response, answers


def test_grading_stops_calling_claude_when_quota_reached(app, world, content, monkeypatch):
    from app.utils import grading_tasks
    calls = []
    monkeypatch.setattr(grading_tasks, 'grade_open_question',
                        lambda *a, **k: calls.append(1) or {'score': 2.0, 'feedback': 'ok'})
    tenant = world['lycee_a']
    tenant.monthly_ai_corrections = 1
    db.session.commit()
    response, answers = _open_quiz_response(world, content['quiz_a'], 2)

    grading_tasks.grade_quiz_async(app, response.id, answers)
    db.session.expire_all()  # grading ran in its own app context

    assert len(calls) == 1
    assert reload_tenant(tenant).used_ai_corrections == 1
    feedbacks = [db.session.get(Answer, a['answer_id']).ai_feedback for a in answers]
    assert 'Quota' in feedbacks[1]
    assert db.session.get(QuizResponse, response.id).grading_status == QuizResponse.STATUS_REVIEW


def test_instructor_grading_clears_review_status(app, world, content, login, monkeypatch):
    from app.utils import grading_tasks
    monkeypatch.setattr(grading_tasks, 'grade_open_question', lambda *a, **k: {'score': 2.0, 'feedback': 'ok'})
    world['lycee_a'].monthly_ai_corrections = 1
    db.session.commit()
    response, answers = _open_quiz_response(world, content['quiz_a'], 2)
    grading_tasks.grade_quiz_async(app, response.id, answers)
    db.session.expire_all()  # grading ran in its own app context

    client = login(world['prof_3a'])
    results = client.get(f"/admin/quiz/{content['quiz_a'].get_url_identifier()}/results").get_data(as_text=True)
    assert 'A corriger' in results
    assert 'copie(s) a corriger' in client.get('/admin/dashboard').get_data(as_text=True)

    client.post(f'/admin/response/{response.get_url_identifier()}/edit',
                data={f"score_{a['answer_id']}": '1' for a in answers})
    assert db.session.get(QuizResponse, response.id).grading_status == QuizResponse.STATUS_COMPLETED


# ==================== joining groups ====================

def test_user_limit_blocks_new_members_but_not_existing_ones(world, login):
    tenant = world['lycee_a']
    tenant.max_users = tenant.get_users_count()
    db.session.commit()

    assert world['g3b'].join_error() is not None           # brand new account
    assert world['g3b'].join_error(world['eleve_3a']) is None  # already in lycee_a


def test_register_refused_when_subscription_expired(world, client):
    world['lycee_a'].subscription_expires_at = date.today() - timedelta(days=1)
    db.session.commit()

    client.post('/register', data={
        'username': 'newbie', 'first_name': 'N', 'last_name': 'B', 'email': 'newbie@test.local',
        'password': 'password1', 'password_confirm': 'password1', 'join_code': 'CODE3A',
    })

    assert User.query.filter_by(username='newbie').first() is None


def test_join_group_refused_when_tenant_full(world, login):
    outsider = User(username='outsider', email='outsider@test.local')
    outsider.set_password('password')
    db.session.add(outsider)
    tenant = world['lycee_a']
    tenant.max_users = tenant.get_users_count()
    db.session.commit()

    login(outsider).post('/join-group', data={'join_code': 'CODE3A'})

    assert not outsider.is_member_of_group(world['g3a'].id)


def test_bulk_add_respects_tenant_user_limit(world, login):
    lycee_b = world['lycee_b']
    lycee_b.max_users = lycee_b.get_users_count()
    db.session.commit()

    login(world['root']).post('/admin/users/bulk-change-group', data={
        'user_ids': [world['eleve_3a'].id], 'action': 'add', 'group_id': world['g2c'].id,
    })

    assert not world['eleve_3a'].is_member_of_group(world['g2c'].id)


# ==================== groups and quizzes limits ====================

def test_create_group_respects_max_groups(world, login):
    tenant = world['lycee_a']
    tenant.max_groups = 2  # 3A + 3B already
    db.session.commit()

    login(world['dir_a']).post('/admin/group/create', data={'name': '3C', 'tenant_id': tenant.id})

    assert Group.query.filter_by(name='3C').first() is None


def test_duplicate_quiz_respects_max_quizzes_and_keeps_tenant(world, content, login):
    client = login(world['dir_a'])
    client.post(f"/admin/quiz/{content['quiz_a'].get_url_identifier()}/duplicate")
    copy = Quiz.query.filter_by(title='Quiz Alpha (copie)').first()
    assert copy is not None and copy.tenant_id == world['lycee_a'].id

    world['lycee_a'].max_quizzes = Quiz.query.filter_by(tenant_id=world['lycee_a'].id).count()
    db.session.commit()
    client.post(f"/admin/quiz/{content['quiz_a'].get_url_identifier()}/duplicate")
    assert Quiz.query.filter_by(title='Quiz Alpha (copie)').count() == 1
