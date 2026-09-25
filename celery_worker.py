"""Celery worker entry point: `celery -A celery_worker worker` (see entrypoint.sh)."""
from app import create_app

flask_app = create_app()
celery = flask_app.extensions['celery']
