"""
Interview background tasks for async processing with WebSocket notifications.
"""

from datetime import datetime
from app import db, socketio
from app.models.interview import InterviewSession, InterviewMessage, CriterionScore
from app.utils.claude_interviewer import ClaudeInterviewer


def evaluate_interview_async(app, session_id: int):
    """
    Evaluate an interview session asynchronously and notify via WebSocket.

    Args:
        app: Flask application instance
        session_id: InterviewSession ID to evaluate
    """
    with app.app_context():
        try:
            session = InterviewSession.query.get(session_id)
            if not session:
                return

            user_id = session.user_id
            room = f'user_{user_id}'

            # Update status
            session.status = InterviewSession.STATUS_EVALUATING
            db.session.commit()

            # Notify evaluation started
            socketio.emit('evaluation_started', {
                'session_id': session_id,
                'total_criteria': len(session.interview.criteria)
            }, room=room)

            # Run evaluation
            interviewer = ClaudeInterviewer()
            result = interviewer.evaluate_session(session)

            # Save scores
            for i, score_data in enumerate(result.get('scores', [])):
                criterion_score = CriterionScore(
                    session_id=session_id,
                    criterion_id=score_data['criterion_id'],
                    score=score_data['score'],
                    max_score=score_data['max_score'],
                    feedback=score_data.get('feedback', '')
                )
                db.session.add(criterion_score)

                # Emit progress
                socketio.emit('evaluation_progress', {
                    'session_id': session_id,
                    'progress': i + 1,
                    'total': len(result['scores']),
                    'criterion_name': score_data.get('criterion_name', ''),
                    'score': score_data['score'],
                    'max_score': score_data['max_score']
                }, room=room)

            # Update session
            session.status = InterviewSession.STATUS_COMPLETED
            session.total_score = result.get('total_score', 0)
            session.max_score = result.get('max_total', 0)
            session.ai_summary = result.get('summary', '')
            if not session.ended_at:
                session.ended_at = datetime.utcnow()

            db.session.commit()

            # Notify completion
            socketio.emit('evaluation_completed', {
                'session_id': session_id,
                'total_score': session.total_score,
                'max_score': session.max_score,
                'percentage': session.get_score_percentage()
            }, room=room)

        except Exception as e:
            app.logger.error(f"Interview evaluation error: {str(e)}")

            # Update session status to error
            session = InterviewSession.query.get(session_id)
            if session:
                session.status = InterviewSession.STATUS_ERROR
                session.ai_summary = f"Erreur lors de l'evaluation: {str(e)}"
                db.session.commit()

            socketio.emit('evaluation_error', {
                'session_id': session_id,
                'error': str(e)
            }, room=f'user_{session.user_id}' if session else room)


def process_interview_message_async(app, session_id: int, user_content: str, room: str):
    """
    Process a user message and get AI response asynchronously.

    Args:
        app: Flask application instance
        session_id: InterviewSession ID
        user_content: User's message content
        room: WebSocket room to emit to
    """
    with app.app_context():
        try:
            session = InterviewSession.query.get(session_id)
            if not session:
                socketio.emit('error', {'message': 'Session non trouvee'}, room=room)
                return

            if session.status != InterviewSession.STATUS_IN_PROGRESS:
                socketio.emit('error', {'message': 'Session terminee'}, room=room)
                return

            interview = session.interview

            # Check interaction limit
            if session.interaction_count >= interview.max_interactions:
                end_interview_by_limit(app, session, room)
                return

            # Save user message
            user_msg = InterviewMessage(
                session_id=session_id,
                role=InterviewMessage.ROLE_USER,
                content=user_content,
                token_count=len(user_content) // 4
            )
            db.session.add(user_msg)
            session.interaction_count += 1
            session.last_activity_at = datetime.utcnow()
            db.session.commit()

            # Emit typing indicator
            socketio.emit('typing_indicator', {'typing': True}, room=room)

            # Get AI response
            interviewer = ClaudeInterviewer()
            response = interviewer.get_response(session, user_content)

            # Save AI message
            ai_msg = InterviewMessage(
                session_id=session_id,
                role=InterviewMessage.ROLE_ASSISTANT,
                content=response['content'],
                token_count=response.get('token_count', 0),
                contains_end_signal=response.get('end_signal', False)
            )
            db.session.add(ai_msg)
            db.session.commit()

            # Send response to client
            socketio.emit('message_received', {
                'session_id': session_id,
                'content': response['content'],
                'interaction_count': session.interaction_count,
                'max_interactions': interview.max_interactions
            }, room=room)

            # Check for end signal
            if response.get('end_signal') and interview.ai_can_end:
                end_interview_by_ai(app, session, room)

        except Exception as e:
            app.logger.error(f"Interview message error: {str(e)}")
            socketio.emit('error', {'message': str(e)}, room=room)


def end_interview_by_limit(app, session: InterviewSession, room: str):
    """End interview due to interaction limit."""
    session.status = InterviewSession.STATUS_ENDED_BY_LIMIT
    session.end_reason = 'limit'
    session.ended_at = datetime.utcnow()
    db.session.commit()

    socketio.emit('interview_ended', {
        'session_id': session.id,
        'reason': 'limit',
        'message': 'Nombre maximum d\'echanges atteint'
    }, room=room)

    # Trigger evaluation
    socketio.start_background_task(
        evaluate_interview_async,
        app,
        session.id
    )


def end_interview_by_ai(app, session: InterviewSession, room: str):
    """End interview due to AI detecting natural conclusion."""
    session.status = InterviewSession.STATUS_ENDED_BY_AI
    session.end_reason = 'ai_natural'
    session.ended_at = datetime.utcnow()
    db.session.commit()

    socketio.emit('interview_ended', {
        'session_id': session.id,
        'reason': 'ai_natural',
        'message': 'L\'entretien s\'est termine naturellement'
    }, room=room)

    # Trigger evaluation
    socketio.start_background_task(
        evaluate_interview_async,
        app,
        session.id
    )


def end_interview_by_timeout(app, session: InterviewSession, room: str):
    """End interview due to timeout."""
    session.status = InterviewSession.STATUS_ENDED_BY_TIMEOUT
    session.end_reason = 'timeout'
    session.ended_at = datetime.utcnow()
    db.session.commit()

    socketio.emit('interview_ended', {
        'session_id': session.id,
        'reason': 'timeout',
        'message': 'Temps maximum depass\u00e9'
    }, room=room)

    # Trigger evaluation
    socketio.start_background_task(
        evaluate_interview_async,
        app,
        session.id
    )
