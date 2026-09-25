"""Grading under load: no database connection held while waiting for the AI, safe retries."""
import pytest
from sqlalchemy.exc import OperationalError

from app import db
from app.models import Answer, QuizResponse
from app.utils import grading_tasks
from tests.test_grading_trust import paper


def test_no_transaction_open_while_the_ai_answers(app, world, content, monkeypatch):
    seen = []

    def fake_ai(*a, **k):
        seen.append(db.session().in_transaction())
        return {'score': 1.0, 'feedback': 'ok'}
    monkeypatch.setattr(grading_tasks, 'grade_open_question', fake_ai)
    response, answers = paper(world, content['quiz_a'])
    grading_tasks.grade_quiz_async(app, response.id, answers)
    assert seen == [False, False]


def test_a_retry_does_not_grade_answers_twice(app, world, content, monkeypatch):
    calls = []
    monkeypatch.setattr(grading_tasks, 'grade_open_question',
                        lambda *a, **k: calls.append(1) or {'score': 2.0, 'feedback': 'ok'})
    response, answers = paper(world, content['quiz_a'])
    first = db.session.get(Answer, answers[0]['answer_id'])
    first.score, first.ai_feedback = 1.0, 'graded by the first attempt'
    db.session.commit()

    grading_tasks.grade_quiz_async(app, response.id, answers)
    db.session.expire_all()
    assert len(calls) == 1
    assert db.session.get(QuizResponse, response.id).total_score == 3.0


def test_transient_db_error_is_retried_or_recorded(app, world, content, monkeypatch):
    response, answers = paper(world, content['quiz_a'])

    def boom(*a, **k):
        raise OperationalError('SELECT 1', {}, Exception('pool exhausted'))
    monkeypatch.setattr(grading_tasks, '_grade', boom)

    with pytest.raises(OperationalError):  # the worker retries
        grading_tasks.grade_quiz_async(app, response.id, answers, retryable=True)
    assert db.session.get(QuizResponse, response.id).grading_status != QuizResponse.STATUS_ERROR

    grading_tasks.grade_quiz_async(app, response.id, answers, retryable=False)  # last attempt
    db.session.expire_all()
    assert db.session.get(QuizResponse, response.id).grading_status == QuizResponse.STATUS_ERROR


def test_interview_reply_releases_the_connection(app, world, content, monkeypatch):
    from app.models import InterviewSession
    from app.utils import claude_interviewer
    seen = []
    monkeypatch.setattr(claude_interviewer, 'complete', lambda *a, **k: seen.append(db.session().in_transaction()) or 'Bonjour.')
    session = InterviewSession(interview_id=content['itw_a'].id, user_id=world['eleve_3a'].id)
    db.session.add(session)
    db.session.commit()
    claude_interviewer.ClaudeInterviewer().get_response(session, 'Salut')
    assert seen == [False]


def test_reading_the_ai_settings_leaves_no_transaction_open(app):
    """complete() reads the settings right before the slow AI call."""
    from app.utils.ai_client import get_config
    db.session.commit()
    get_config()
    assert not db.session().in_transaction()
