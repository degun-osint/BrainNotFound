"""Background grading tasks with WebSocket notifications."""
from sqlalchemy.exc import DisconnectionError, OperationalError, TimeoutError as SATimeoutError

from app import db, socketio
from app.models.quiz import QuizResponse, Answer
from app.utils.claude_grader import grade_open_question
from flask import current_app


def finish_grading(quiz_response, needs_review):
    """End of AI grading: publish the grade, or leave the paper to a grader.

    A paper waits for a grader when the AI could not grade an answer, or when
    the quiz is in review mode (admin test papers are never held back).
    Graders hear about it in the next digest email.
    """
    quiz = quiz_response.quiz
    if needs_review or (quiz.needs_review and not quiz_response.is_test):
        quiz_response.grading_status = QuizResponse.STATUS_REVIEW
        quiz_response.review_reason = QuizResponse.REVIEW_AI if needs_review else QuizResponse.REVIEW_MODE
        if not quiz_response.is_test:
            quiz.mark_digest_pending()
    else:
        quiz_response.publish()


# Feedback left on answers the AI could not grade (a grader takes over)
QUOTA_FEEDBACK = "Quota mensuel de corrections IA atteint : cette reponse sera corrigee par l'intervenant."
FAILED_FEEDBACK = "Correction automatique impossible : cette reponse sera corrigee par l'intervenant."
HELD_FOR_GRADER = (QUOTA_FEEDBACK, FAILED_FEEDBACK)

# Database hiccups (connection pool exhausted, server gone): worth retrying the task
TRANSIENT_DB_ERRORS = (OperationalError, SATimeoutError, DisconnectionError)


def grade_quiz_async(app, response_id: int, answers_data: list, retryable: bool = False):
    """Grade the open answers of a paper with the AI, notifying the learner via WebSocket.

    A database connection is only held for short reads and writes, never while
    waiting for the AI (seconds per answer): with many papers graded at once,
    holding it exhausted the connection pool and papers failed.

    Answers already graded (a retried task) are not sent to the AI again.
    retryable: on a transient database error, raise it so the caller (Celery)
    retries, instead of marking the paper as failed.
    """
    with app.app_context():
        try:
            _grade(response_id, answers_data)
        except TRANSIENT_DB_ERRORS as e:
            db.session.rollback()
            if retryable:
                current_app.logger.warning(f"Grading of response {response_id} interrupted, will retry: {e}")
                raise
            _mark_error(response_id, e)
        except Exception as e:
            db.session.rollback()
            _mark_error(response_id, e)


def _grade(response_id, answers_data):
    db.session.expire_all()
    quiz_response = db.session.get(QuizResponse, response_id)
    if not quiz_response:
        current_app.logger.error(f"QuizResponse {response_id} not found")
        return
    quiz = quiz_response.quiz
    room = f'user_{quiz_response.user_id}'
    total = quiz_response.grading_total
    severity, mood = quiz.grading_severity or 'modere', quiz.grading_mood or []
    tenant_id = quiz.tenant_id

    quiz_response.grading_status = QuizResponse.STATUS_GRADING
    db.session.commit()
    socketio.emit('grading_started', {'response_id': response_id, 'total': total}, room=room)

    graded_count = 0
    needs_review = False
    for answer_info in answers_data:
        answer_id = answer_info['answer_id']
        answer = db.session.get(Answer, answer_id)
        if not answer:
            current_app.logger.error(f"Answer {answer_id} not found")
            continue
        question = answer.question
        question_text, expected, points = question.question_text, question.expected_answer, question.points
        answer_text = answer.answer_text

        if answer.ai_feedback is not None:
            # Graded by an earlier attempt of this task: keep it
            needs_review = needs_review or answer.ai_feedback in HELD_FOR_GRADER
        elif not answer_text:
            answer.score, answer.ai_feedback = 0.0, "Aucune reponse fournie par l'etudiant."
        elif not expected:
            answer.score = points
            answer.ai_feedback = "Question ouverte sans reponse attendue definie. Points accordes automatiquement."
            current_app.logger.warning(f"Question {question.id} has no expected_answer")
        elif tenant_id and not quiz.tenant.can_use_ai_correction():
            answer.score, answer.ai_feedback = 0.0, QUOTA_FEEDBACK
            needs_review = True
            current_app.logger.warning(f"AI correction quota reached for tenant {tenant_id}")
        else:
            # Release the database connection while the AI answers
            db.session.commit()
            try:
                result = grade_open_question(question_text, expected, answer_text, points,
                                             severity=severity, mood=mood)
            except Exception as e:
                current_app.logger.error(f"Grading error for answer {answer_id}: {e}")
                result = {'score': 0.0, 'feedback': FAILED_FEEDBACK, 'needs_review': True}
            answer = db.session.get(Answer, answer_id)
            answer.score, answer.ai_feedback = result['score'], result['feedback']
            if result.get('needs_review'):
                needs_review = True
            elif tenant_id:
                db.session.get(QuizResponse, response_id).quiz.tenant.increment_ai_corrections()
            current_app.logger.info(f"AI graded answer {answer_id}: score={answer.score}")

        graded_count += 1
        score, max_score = answer.score, answer.max_score
        db.session.get(QuizResponse, response_id).grading_progress = graded_count
        db.session.commit()
        socketio.emit('grading_progress', {
            'response_id': response_id, 'progress': graded_count, 'total': total,
            'question_text': question_text[:50] + '...' if len(question_text) > 50 else question_text,
            'score': score, 'max_score': max_score,
        }, room=room)

    quiz_response = db.session.get(QuizResponse, response_id)
    quiz_response.recompute_total()  # MCQ + open answers
    finish_grading(quiz_response, needs_review)
    total_score, max_total = quiz_response.total_score, quiz_response.max_score
    in_review = quiz_response.grading_status == QuizResponse.STATUS_REVIEW
    db.session.commit()
    current_app.logger.info(f"Grading complete for response {response_id}: total={total_score}")
    socketio.emit('grading_completed', {
        'response_id': response_id, 'total_score': total_score, 'max_score': max_total,
        'percentage': (total_score / max_total * 100) if max_total > 0 else 0,
        'needs_review': in_review,
    }, room=room)


def _mark_error(response_id, error):
    """The paper could not be graded: say so to the learner (a grader can regrade it)."""
    current_app.logger.error(f"Grading task error for response {response_id}: {error}")
    try:
        quiz_response = db.session.get(QuizResponse, response_id)
        if quiz_response:
            quiz_response.grading_status = QuizResponse.STATUS_ERROR
            db.session.commit()
            socketio.emit('grading_error', {'response_id': response_id, 'error': str(error)},
                          room=f'user_{quiz_response.user_id}')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Could not mark response {response_id} as failed: {e}")
