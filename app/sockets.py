"""WebSocket event handlers for real-time features."""
from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room, emit
from app import socketio


@socketio.on('connect')
def handle_connect():
    """Handle client connection - join user's private room."""
    if current_user.is_authenticated:
        room = f'user_{current_user.id}'
        join_room(room)
        emit('connected', {'room': room, 'user_id': current_user.id})
    else:
        emit('error', {'message': 'Non authentifie'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    if current_user.is_authenticated:
        room = f'user_{current_user.id}'
        leave_room(room)


@socketio.on('join_grading')
def handle_join_grading(data):
    """Join a specific grading session room."""
    if current_user.is_authenticated:
        response_id = data.get('response_id')
        if response_id:
            room = f'grading_{response_id}'
            join_room(room)
            emit('joined_grading', {'response_id': response_id})


# ============================================================================
# Interview WebSocket Events
# ============================================================================

@socketio.on('join_interview')
def handle_join_interview(data):
    """Join an interview session room."""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Non authentifie'})
        return

    session_id = data.get('session_id')
    if session_id:
        from app.models.interview import InterviewSession
        session = InterviewSession.query.get(session_id)

        if session and session.user_id == current_user.id:
            room = f'interview_{session_id}'
            join_room(room)
            emit('joined_interview', {'session_id': session_id})
        else:
            emit('error', {'message': 'Session non autorisee'})


@socketio.on('leave_interview')
def handle_leave_interview(data):
    """Leave an interview session room."""
    if current_user.is_authenticated:
        session_id = data.get('session_id')
        if session_id:
            room = f'interview_{session_id}'
            leave_room(room)


@socketio.on('send_message')
def handle_send_message(data):
    """Handle student message in interview."""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Non authentifie'})
        return

    session_id = data.get('session_id')
    content = data.get('content', '').strip()

    if not session_id or not content:
        emit('error', {'message': 'Donnees manquantes'})
        return

    from app.models.interview import InterviewSession
    from flask import current_app

    session = InterviewSession.query.get(session_id)

    if not session:
        emit('error', {'message': 'Session non trouvee'})
        return

    if session.user_id != current_user.id:
        emit('error', {'message': 'Session non autorisee'})
        return

    if session.status != InterviewSession.STATUS_IN_PROGRESS:
        emit('error', {'message': 'Session terminee'})
        return

    # Check interaction limit
    if session.interaction_count >= session.interview.max_interactions:
        emit('error', {'message': 'Limite d\'echanges atteinte'})
        return

    # Process message in background
    room = f'interview_{session_id}'
    from app.utils.interview_tasks import process_interview_message_async
    socketio.start_background_task(
        process_interview_message_async,
        current_app._get_current_object(),
        session_id,
        content,
        room
    )
