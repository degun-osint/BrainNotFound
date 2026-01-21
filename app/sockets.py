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
