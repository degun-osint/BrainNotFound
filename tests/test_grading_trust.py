"""Grading trust: review mode, graders, validation, contests, grader digest."""
from datetime import datetime, timedelta

import pytest

from app import db, mail
from app.models import Answer, AnswerContest, Question, Quiz, QuizResponse
from app.utils import grading_tasks


def paper(world, quiz, learner='eleve_3a', n_answers=2):
    """A submitted paper with n open answers, not graded yet. Returns (response, answers_data)."""
    response = QuizResponse(user_id=world[learner].id, quiz_id=quiz.id, max_score=2 * n_answers)
    db.session.add(response)
    db.session.flush()
    answers = []
    for i in range(n_answers):
        q = Question(quiz_id=quiz.id, question_type='open', question_text=f'Q{i}', points=2,
                     expected_answer='42', order=i)
        db.session.add(q)
        db.session.flush()
        a = Answer(quiz_response_id=response.id, question_id=q.id, answer_text='42', max_score=2)
        db.session.add(a)
        db.session.flush()
        answers.append({'answer_id': a.id})
    db.session.commit()
    return response, answers


@pytest.fixture
def ai_grades(monkeypatch):
    """The AI gives 1.5/2 to every answer (or fails when told to)."""
    state = {'fail': False}

    def fake(*a, **k):
        if state['fail']:
            return {'score': 0.0, 'feedback': 'Correction automatique impossible', 'needs_review': True}
        return {'score': 1.5, 'feedback': 'ok'}
    monkeypatch.setattr(grading_tasks, 'grade_open_question', fake)
    return state


def grade(app, response, answers):
    grading_tasks.grade_quiz_async(app, response.id, answers)
    db.session.expire_all()  # grading ran in its own app context
    return db.session.get(QuizResponse, response.id)


def published(world, content, app, ai_grades, days=7):
    quiz = content['quiz_a']
    quiz.contest_days = days
    db.session.commit()
    response, answers = paper(world, quiz)
    return grade(app, response, answers), answers


# ==================== grading modes ====================

def test_direct_mode_publishes_the_ai_grade(app, world, content, ai_grades):
    response, _ = published(world, content, app, ai_grades)
    assert response.grading_status == QuizResponse.STATUS_COMPLETED
    assert response.graded_at is not None and response.total_score == 3.0


def test_review_mode_holds_the_paper_for_a_grader(app, world, content, ai_grades, login):
    quiz = content['quiz_a']
    quiz.grading_mode = Quiz.GRADING_REVIEW
    db.session.commit()
    response, answers = paper(world, quiz)
    response = grade(app, response, answers)

    assert response.grading_status == QuizResponse.STATUS_REVIEW
    assert response.review_reason == QuizResponse.REVIEW_MODE
    assert response.total_score == 3.0  # provisional grade, visible to the learner
    assert db.session.get(Quiz, quiz.id).digest_pending_since is not None
    html = login(world['eleve_3a']).get(f'/quiz/result/{response.get_url_identifier()}').get_data(as_text=True)
    assert 'un correcteur doit encore valider' in html


def test_ai_failure_is_a_paper_to_grade_even_in_direct_mode(app, world, content, ai_grades):
    ai_grades['fail'] = True
    response, answers = paper(world, content['quiz_a'])
    response = grade(app, response, answers)
    assert response.grading_status == QuizResponse.STATUS_REVIEW
    assert response.review_reason == QuizResponse.REVIEW_AI


def test_validate_one_paper(app, world, content, ai_grades, login):
    content['quiz_a'].grading_mode = Quiz.GRADING_REVIEW
    db.session.commit()
    response, answers = paper(world, content['quiz_a'])
    grade(app, response, answers)

    login(world['prof_3a']).post(f'/admin/response/{response.get_url_identifier()}/validate')
    response = db.session.get(QuizResponse, response.id)
    assert response.grading_status == QuizResponse.STATUS_COMPLETED
    assert response.reviewed_by_id == world['prof_3a'].id and response.graded_at is not None


def test_validate_all_skips_papers_the_ai_could_not_grade(app, world, content, ai_grades, login):
    quiz = content['quiz_a']
    quiz.grading_mode = Quiz.GRADING_REVIEW
    db.session.commit()
    ok, answers = paper(world, quiz, 'eleve_3a')
    grade(app, ok, answers)
    ai_grades['fail'] = True
    failed, answers = paper(world, quiz, 'eleve_ab')
    grade(app, failed, answers)

    login(world['prof_3a']).post(f'/admin/quiz/{quiz.get_url_identifier()}/validate-all')
    assert db.session.get(QuizResponse, ok.id).grading_status == QuizResponse.STATUS_COMPLETED
    assert db.session.get(QuizResponse, failed.id).grading_status == QuizResponse.STATUS_REVIEW


def test_saving_scores_does_not_validate(app, world, content, ai_grades, login):
    content['quiz_a'].grading_mode = Quiz.GRADING_REVIEW
    db.session.commit()
    response, answers = paper(world, content['quiz_a'])
    grade(app, response, answers)
    client = login(world['prof_3a'])
    url = f'/admin/response/{response.get_url_identifier()}/edit'

    client.post(url, data={f"score_{answers[0]['answer_id']}": '2'})
    assert db.session.get(QuizResponse, response.id).grading_status == QuizResponse.STATUS_REVIEW
    client.post(url, data={f"score_{answers[0]['answer_id']}": '2', 'action': 'validate'})
    response = db.session.get(QuizResponse, response.id)
    assert response.grading_status == QuizResponse.STATUS_COMPLETED and response.total_score == 3.5


# ==================== graders ====================

def test_designated_grader_sees_and_grades_every_paper(app, world, content, ai_grades, login):
    quiz = content['quiz_a']
    response, answers = paper(world, quiz)
    grade(app, response, answers)
    outsider = world['prof_3b']  # instructor of 3B, the quiz is assigned to 3A only
    client = login(outsider)
    assert client.get(f'/admin/quiz/{quiz.get_url_identifier()}/results').status_code == 302

    quiz.graders.append(outsider)
    db.session.commit()
    html = client.get(f'/admin/quiz/{quiz.get_url_identifier()}/results').get_data(as_text=True)
    assert 'eleve_3a' in html
    client.post(f'/admin/response/{response.get_url_identifier()}/edit',
                data={f"score_{answers[0]['answer_id']}": '0'})
    assert db.session.get(Answer, answers[0]['answer_id']).score == 0


def test_quiz_form_sets_mode_delay_and_graders_in_scope(world, content, login):
    quiz = content['quiz_a']
    quiz.graders.append(world['dir_b'])  # named by someone else, outside dir_a's scope
    db.session.commit()
    client = login(world['dir_a'])
    client.post(f'/admin/quiz/{quiz.get_url_identifier()}/edit', data={
        'markdown_content': '# Quiz Alpha\n\n## QCM - Q [1 point]\n- [x] a\n- [ ] b\n',
        'group_ids': [world['g3a'].id],
        'grading_mode': 'review', 'contest_days': '3',
        'grader_ids': [world['prof_3b'].id, world['eleve_3a'].id, 999999],
    })
    quiz = db.session.get(Quiz, quiz.id)
    assert quiz.grading_mode == 'review' and quiz.contest_days == 3
    # dir_b kept (outside our scope), a learner and an unknown id ignored
    assert {u.username for u in quiz.graders} == {'prof_3b', 'dir_b'}


def test_grader_candidates_are_instructors_and_admins_in_scope(world, login):
    html = login(world['dir_a']).get('/admin/quiz/create').get_data(as_text=True)
    section = html.split('name="grader_ids"', 1)[1] if 'name="grader_ids"' in html else ''
    candidates = html[html.index('name="grader_ids"') - 200:] if section else ''
    for name in ('prof_3a@test.local', 'prof_3b@test.local'):
        assert name in candidates
    # dir_a writes the quiz: grader anyway, not offered
    for name in ('dir_a@test.local', 'dir_b@test.local', 'eleve_3a@test.local', 'root@test.local'):
        assert name not in candidates


# ==================== contests ====================

def contest(client, response, answer_id, reason='Ma reponse cite bien 42'):
    return client.post(f'/quiz/result/{response.get_url_identifier()}/contest/{answer_id}', data={'reason': reason})


def test_learner_contests_once_within_the_delay(app, world, content, ai_grades, login):
    response, answers = published(world, content, app, ai_grades)
    client = login(world['eleve_3a'])
    contest(client, response, answers[0]['answer_id'])
    contest(client, response, answers[0]['answer_id'], 'encore')
    assert AnswerContest.query.count() == 1
    assert db.session.get(Quiz, content['quiz_a'].id).digest_pending_since is not None


def test_no_contest_after_the_delay_or_before_publication(app, world, content, ai_grades, login):
    response, answers = published(world, content, app, ai_grades)
    response.graded_at = datetime.utcnow() - timedelta(days=8)
    db.session.commit()
    contest(login(world['eleve_3a']), response, answers[0]['answer_id'])
    assert AnswerContest.query.count() == 0

    response.grading_status = QuizResponse.STATUS_REVIEW
    response.graded_at = datetime.utcnow()
    db.session.commit()
    contest(login(world['eleve_3a']), response, answers[0]['answer_id'])
    assert AnswerContest.query.count() == 0


def test_no_contest_when_disabled_or_on_someone_else_paper(app, world, content, ai_grades, login):
    response, answers = published(world, content, app, ai_grades, days=0)
    contest(login(world['eleve_3a']), response, answers[0]['answer_id'])
    content['quiz_a'].contest_days = 7
    db.session.commit()
    contest(login(world['eleve_ab']), response, answers[0]['answer_id'])
    assert AnswerContest.query.count() == 0


@pytest.mark.parametrize('decision, final_score', [('accept', 2.0), ('reject', 1.5)])
def test_grader_resolves_a_contest(app, world, content, ai_grades, login, decision, final_score):
    response, answers = published(world, content, app, ai_grades)
    answer_id = answers[0]['answer_id']
    contest(login(world['eleve_3a']), response, answer_id)

    login(world['prof_3a']).post(f'/admin/response/{response.get_url_identifier()}/edit', data={
        f'score_{answer_id}': '2', f'contest_{answer_id}': decision, f'contest_reply_{answer_id}': 'Vu.'})
    c = AnswerContest.query.one()
    assert c.status == ('accepted' if decision == 'accept' else 'rejected')
    assert c.reply == 'Vu.' and c.resolved_by_id == world['prof_3a'].id
    assert db.session.get(Answer, answer_id).score == final_score
    assert db.session.get(QuizResponse, response.id).total_score == final_score + 1.5
    html = login(world['eleve_3a']).get(f'/quiz/result/{response.get_url_identifier()}').get_data(as_text=True)
    assert 'Vu.' in html


def test_results_filters_and_dashboard(app, world, content, ai_grades, login):
    response, answers = published(world, content, app, ai_grades)
    contest(login(world['eleve_3a']), response, answers[0]['answer_id'])
    client = login(world['prof_3a'])
    url = f"/admin/quiz/{content['quiz_a'].get_url_identifier()}/results"
    assert 'eleve_3a' in client.get(url + '?status=contests').get_data(as_text=True)
    assert 'eleve_3a' not in client.get(url + '?status=review').get_data(as_text=True)
    dashboard = client.get('/admin/dashboard').get_data(as_text=True)
    assert 'Corrections a traiter' in dashboard and 'Quiz Alpha' in dashboard


def test_other_organization_admin_cannot_open_a_paper(app, world, content, ai_grades, login):
    """A tenant admin of another organization can't open a learner's paper through a shared quiz."""
    response, _ = paper(world, content['quiz_shared'])
    assert login(world['dir_b']).get(f'/quiz/result/{response.get_url_identifier()}').status_code == 302


# ==================== digest ====================

def test_digest_groups_events_and_is_throttled(app, world, content, ai_grades, login):
    from app.utils.grading_digest import send_due_digests
    app.config['PUBLIC_URL'] = 'https://quiz.example.com'
    quiz = content['quiz_a']
    quiz.created_by_id = world['prof_3a'].id
    quiz.graders.append(world['prof_3b'])
    quiz.grading_mode = Quiz.GRADING_REVIEW
    db.session.commit()
    for learner in ('eleve_3a', 'eleve_ab'):
        response, answers = paper(world, quiz, learner)
        grade(app, response, answers)

    with mail.record_messages() as outbox:
        assert send_due_digests() == 1
        assert send_due_digests() == 0  # nothing new
    msg = outbox[0]
    assert set(msg.recipients) == {'prof_3a@test.local', 'prof_3b@test.local'}
    assert '2 copie(s)' in msg.subject
    assert f'https://quiz.example.com/admin/quiz/{quiz.get_url_identifier()}/results' in msg.body

    # A new event within the delay waits, then goes out
    response, answers = paper(world, quiz, 'eleve_3a_3b')
    grade(app, response, answers)
    with mail.record_messages() as outbox:
        assert send_due_digests() == 0
        assert send_due_digests(now=datetime.utcnow() + timedelta(minutes=31)) == 1
    assert '3 copie(s)' in outbox[0].subject


def test_deleting_a_grader_keeps_the_quiz_and_their_work(app, world, content, ai_grades, login):
    from app.utils.deletion import delete_user_account
    response, answers = published(world, content, app, ai_grades)
    grader = world['prof_3b']
    content['quiz_a'].graders.append(grader)
    contest(login(world['eleve_3a']), response, answers[0]['answer_id'])
    login(grader).post(f'/admin/response/{response.get_url_identifier()}/edit', data={
        f"contest_{answers[0]['answer_id']}": 'reject'})
    grader_id = grader.id

    delete_user_account(db.session.get(type(grader), grader_id))
    db.session.commit()
    assert db.session.get(Quiz, content['quiz_a'].id).graders.count() == 0
    assert AnswerContest.query.one().resolved_by_id is None
