"""Background grading tasks with WebSocket notifications."""
from app import db, socketio
from app.models.quiz import QuizResponse, Answer, Question
from app.utils.claude_grader import grade_open_question
from flask import current_app


def grade_quiz_async(app, response_id: int, answers_data: list):
    """
    Grade a quiz asynchronously and notify via WebSocket.

    Args:
        app: Flask app instance (needed for app context)
        response_id: QuizResponse ID
        answers_data: List of dicts with answer info to grade
    """
    with app.app_context():
        try:
            # Refresh the quiz_response from the database to get committed data
            db.session.expire_all()

            quiz_response = QuizResponse.query.get(response_id)
            if not quiz_response:
                current_app.logger.error(f"QuizResponse {response_id} not found")
                return

            quiz = quiz_response.quiz
            user_id = quiz_response.user_id
            room = f'user_{user_id}'

            # Store the MCQ score that was already calculated
            mcq_score = quiz_response.total_score or 0.0

            current_app.logger.info(f"Starting async grading for response {response_id}, MCQ score: {mcq_score}")

            # Update status to grading
            quiz_response.grading_status = QuizResponse.STATUS_GRADING
            db.session.commit()

            # Notify client that grading started
            socketio.emit('grading_started', {
                'response_id': response_id,
                'total': quiz_response.grading_total
            }, room=room)

            open_score = 0.0
            graded_count = 0

            for answer_info in answers_data:
                answer_id = answer_info['answer_id']

                # Refresh answer from database
                db.session.expire_all()
                answer = Answer.query.get(answer_id)

                if not answer:
                    current_app.logger.error(f"Answer {answer_id} not found")
                    continue

                question = answer.question

                current_app.logger.info(f"Grading answer {answer_id}: text='{answer.answer_text[:50] if answer.answer_text else 'None'}...', expected='{question.expected_answer[:50] if question.expected_answer else 'None'}...'")

                # Grade open question with AI
                if answer.answer_text:
                    if question.expected_answer:
                        try:
                            grading_result = grade_open_question(
                                question.question_text,
                                question.expected_answer,
                                answer.answer_text,
                                question.points,
                                severity=quiz.grading_severity or 'modere',
                                mood=quiz.grading_mood or []
                            )
                            answer.score = grading_result['score']
                            answer.ai_feedback = grading_result['feedback']
                            current_app.logger.info(f"AI graded answer {answer_id}: score={answer.score}")
                        except Exception as e:
                            current_app.logger.error(f"Grading error for answer {answer_id}: {e}")
                            answer.score = 0.0
                            answer.ai_feedback = f"Erreur lors de la correction: {str(e)}"
                    else:
                        # No expected answer defined - give full points with note
                        answer.score = question.points
                        answer.ai_feedback = "Question ouverte sans reponse attendue definie. Points accordes automatiquement."
                        current_app.logger.warning(f"Question {question.id} has no expected_answer")
                else:
                    answer.score = 0.0
                    answer.ai_feedback = "Aucune reponse fournie par l'etudiant."

                open_score += answer.score
                graded_count += 1

                # Update progress
                quiz_response.grading_progress = graded_count
                db.session.commit()

                # Notify client of progress
                socketio.emit('grading_progress', {
                    'response_id': response_id,
                    'progress': graded_count,
                    'total': quiz_response.grading_total,
                    'question_text': question.question_text[:50] + '...' if len(question.question_text) > 50 else question.question_text,
                    'score': answer.score,
                    'max_score': answer.max_score
                }, room=room)

            # Finalize grading - ADD open score to MCQ score (don't overwrite!)
            total_score = mcq_score + open_score
            quiz_response.total_score = total_score
            quiz_response.grading_status = QuizResponse.STATUS_COMPLETED
            db.session.commit()

            current_app.logger.info(f"Grading complete for response {response_id}: MCQ={mcq_score}, Open={open_score}, Total={total_score}")

            # Notify client that grading is complete
            socketio.emit('grading_completed', {
                'response_id': response_id,
                'total_score': total_score,
                'max_score': quiz_response.max_score,
                'percentage': (total_score / quiz_response.max_score * 100) if quiz_response.max_score > 0 else 0
            }, room=room)

        except Exception as e:
            current_app.logger.error(f"Grading task error: {e}")
            try:
                quiz_response = QuizResponse.query.get(response_id)
                if quiz_response:
                    quiz_response.grading_status = QuizResponse.STATUS_ERROR
                    db.session.commit()

                    socketio.emit('grading_error', {
                        'response_id': response_id,
                        'error': str(e)
                    }, room=f'user_{quiz_response.user_id}')
            except:
                pass
