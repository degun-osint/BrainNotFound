"""Background work: AI grading, interviews, emails and the periodic tick.

With REDIS_URL set, tasks go to the Celery worker (container `worker`), and
Socket.IO events it emits reach the browsers through Redis. Without it (small
installs, development, tests), the same tasks run in the web process as
background greenlets, as before.

Tasks take plain ids and strings (they cross a queue), and run inside an app
context (FlaskTask).
"""
import logging

from celery import Celery, Task, shared_task
from celery.signals import worker_ready
from flask import current_app

logger = logging.getLogger(__name__)

TICK_SECONDS = 300  # digest emails and scheduled backups are checked every 5 minutes


def init_celery(app):
    """Celery app bound to the Flask app (app.extensions['celery'])."""
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    broker = app.config.get('REDIS_URL')
    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.conf.update(
        broker_url=broker or 'memory://',
        task_ignore_result=True,
        # Acknowledge once done: a task interrupted by a restart is redelivered
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
    )
    celery_app.set_default()
    app.extensions['celery'] = celery_app
    return celery_app


def run_task(task, *args):
    """Queue a task for the worker, or run it in the background of this process without Redis."""
    if current_app.config.get('REDIS_URL'):
        task.delay(*args)
    else:
        from app import socketio
        socketio.start_background_task(task, *args)


# ==================== Tasks ====================

@shared_task(name='app.tasks.grade_quiz')
def grade_quiz(response_id, answers_data):
    from app.utils.grading_tasks import grade_quiz_async
    grade_quiz_async(current_app._get_current_object(), response_id, answers_data)


@shared_task(name='app.tasks.evaluate_interview')
def evaluate_interview(session_id):
    from app.utils.interview_tasks import evaluate_interview_async
    evaluate_interview_async(current_app._get_current_object(), session_id)


@shared_task(name='app.tasks.interview_reply')
def interview_reply(session_id, content, room):
    from app.utils.interview_tasks import process_interview_message_async
    process_interview_message_async(current_app._get_current_object(), session_id, content, room)


@shared_task(name='app.tasks.send_email')
def send_email(subject, recipients, body, html=None, sender=None):
    from flask_mail import Message
    from app import mail
    try:
        mail.send(Message(subject=subject, recipients=recipients, body=body, html=html, sender=sender))
    except Exception as e:
        logger.error(f'Failed to send email "{subject}" to {recipients}: {e}')


@shared_task(name='app.tasks.tick')
def tick():
    """Every TICK_SECONDS: grader digests, and the scheduled backup when it is due."""
    from app.utils.grading_digest import send_due_digests
    from app.utils.backup_scheduler import run_backup_if_due
    for job in (send_due_digests, run_backup_if_due):
        try:
            job()
        except Exception as e:
            logger.error(f'Periodic job {job.__name__} failed: {e}')


def start_tick_loop():
    """Run tick() every TICK_SECONDS in a background greenlet of this process.

    Started by the Celery worker when Redis is configured (a single worker container:
    Celery beat can't share a gevent worker), otherwise by the web process.
    """
    from app import socketio

    def loop():
        while True:
            socketio.sleep(TICK_SECONDS)
            tick()

    socketio.start_background_task(loop)
    logger.info(f'Periodic tick started (every {TICK_SECONDS} s)')


@worker_ready.connect
def _start_tick_in_worker(sender=None, **kwargs):
    start_tick_loop()
