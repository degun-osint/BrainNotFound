"""Background tasks: dispatch to Celery or to the web process, periodic tick, backup schedule."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import db
from app.utils.backup_scheduler import backup_due, last_slot, next_slot

PARIS = timezone(timedelta(hours=2))


def settings(**kw):
    base = dict(ftp_enabled=True, backup_frequency='daily', backup_hour=3, backup_day=0, last_backup_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def at(day, hour, minute=0):
    """2026-09-<day> <hour>:<minute> in Paris (a Monday is the 21st)."""
    return datetime(2026, 9, day, hour, minute, tzinfo=PARIS)


# ==================== backup schedule ====================

@pytest.mark.parametrize('kw, now, expected', [
    ({}, at(25, 10), at(25, 3)),
    ({}, at(25, 2), at(24, 3)),
    ({'backup_hour': 0}, at(25, 10), at(25, 0)),        # midnight is not "unset" (used to become 3 am)
    ({'backup_frequency': 'hourly'}, at(25, 10, 40), at(25, 10)),
    ({'backup_frequency': 'weekly', 'backup_day': 0}, at(25, 10), at(21, 3)),   # last Monday
    ({'backup_frequency': 'weekly', 'backup_day': 4}, at(25, 2), at(18, 3)),    # Friday, before 3 am
])
def test_last_slot(kw, now, expected):
    assert last_slot(settings(**kw), now) == expected


def test_next_slot():
    assert next_slot(settings(), at(25, 10)) == at(26, 3)


def utc(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def test_backup_due():
    now = at(25, 3, 5)
    assert backup_due(settings(), now)                                        # never backed up
    assert not backup_due(settings(ftp_enabled=False), now)
    assert backup_due(settings(last_backup_at=utc(at(24, 3, 1))), now)        # yesterday's run: due
    assert not backup_due(settings(last_backup_at=utc(at(25, 3, 1))), now)    # already done this slot
    assert backup_due(settings(last_backup_at=utc(at(20, 3))), at(25, 18))    # missed slots: caught up


def test_run_backup_if_due_only_runs_when_due(app, monkeypatch):
    from app.models import SiteSettings
    from app.utils import backup_manager, backup_scheduler
    runs = []

    class FakeManager:
        def __init__(self, s):
            self.s = s

        def run_backup(self):
            runs.append(1)
            self.s.last_backup_at = datetime.utcnow()
            db.session.commit()
            return {'success': True, 'message': 'ok'}
    monkeypatch.setattr(backup_manager, 'BackupManager', FakeManager)
    s = SiteSettings.get_settings()
    s.ftp_enabled = True
    db.session.commit()

    assert backup_scheduler.run_backup_if_due() is True
    assert backup_scheduler.run_backup_if_due() is False
    assert len(runs) == 1


# ==================== dispatch ====================

def test_run_task_without_redis_runs_in_the_web_process(app, monkeypatch):
    from app import socketio
    from app.tasks import run_task, send_email
    started = []
    monkeypatch.setattr(socketio, 'start_background_task', lambda f, *a: started.append((f, a)))
    run_task(send_email, 'S', ['a@x'], 'body')
    assert started == [(send_email, ('S', ['a@x'], 'body'))]


def test_run_task_with_redis_queues_for_the_worker(app, monkeypatch):
    from app.tasks import run_task, send_email
    queued = []
    monkeypatch.setattr(send_email, 'delay', lambda *a: queued.append(a))
    app.config['REDIS_URL'] = 'redis://redis:6379/0'
    try:
        run_task(send_email, 'S', ['a@x'], 'body')
    finally:
        app.config['REDIS_URL'] = ''
    assert queued == [('S', ['a@x'], 'body')]


def test_tasks_run_in_an_app_context(app):
    """A task called directly (fallback, or by the worker) gets its own app context."""
    from app import mail
    from app.tasks import send_email
    with mail.record_messages() as outbox:
        send_email('Sujet', ['a@x.test'], 'Corps', '<p>Corps</p>')
    assert outbox[0].subject == 'Sujet' and outbox[0].html == '<p>Corps</p>'


def test_emails_go_through_the_task(app, world, monkeypatch):
    from app.tasks import send_email
    from app.utils import email_sender
    sent = []
    monkeypatch.setattr('app.tasks.run_task', lambda task, *a: sent.append((task, a)))
    with app.test_request_context():
        email_sender.send_reset_email(world['eleve_3a'], by_admin=True)
    task, args = sent[0]
    assert task is send_email and args[1] == ['eleve_3a@test.local'] and '/reset-password/' in args[2]


def test_tick_survives_a_failing_job(app, monkeypatch):
    from app import tasks
    calls = []
    monkeypatch.setattr('app.utils.grading_digest.send_due_digests', lambda: 1 / 0)
    monkeypatch.setattr('app.utils.backup_scheduler.run_backup_if_due', lambda: calls.append('backup'))
    tasks.tick()
    assert calls == ['backup']


def test_only_one_worker_runs_each_tick(app, monkeypatch):
    """With Redis, workers race for a lock: the tick runs once per period."""
    import redis
    from app import tasks
    store = {}

    class FakeRedis:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True
    monkeypatch.setattr(redis.Redis, 'from_url', staticmethod(lambda url: FakeRedis()))
    runs = []
    monkeypatch.setattr('app.utils.grading_digest.send_due_digests', lambda: runs.append('digest'))
    monkeypatch.setattr('app.utils.backup_scheduler.run_backup_if_due', lambda: None)
    app.config['REDIS_URL'] = 'redis://redis:6379/0'
    try:
        tasks.tick()  # worker 1
        tasks.tick()  # worker 2, same period
    finally:
        app.config['REDIS_URL'] = ''
    assert runs == ['digest']
