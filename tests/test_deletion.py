"""Deleting users and whole organizations."""
import pytest

from app import db
from app.models import Group, Interview, Quiz, QuizResponse, Tenant, User
from app.models.interview import InterviewMessage, InterviewSession
from app.utils.backup_manager import BackupManager


@pytest.fixture
def no_backup(monkeypatch, tmp_path):
    """Deleting an organization takes a backup first: fake it (no mysqldump in tests)."""
    made = []

    def create_backup(self):
        path = tmp_path / 'backup_quizdb_20260101_000000.tar.gz'
        path.write_bytes(b'x')
        made.append(path)
        return True, str(path), 'ok', 1
    monkeypatch.setattr(BackupManager, 'create_backup', create_backup)
    monkeypatch.setattr(BackupManager, 'keep_locally', lambda self, path, prefix='backup_': path)
    return made


def with_activity(world, content):
    """Quiz responses and an interview session with messages for learners of lycee_a."""
    for name in ('eleve_3a', 'eleve_ab'):
        db.session.add(QuizResponse(user_id=world[name].id, quiz_id=content['quiz_a'].id))
    session = InterviewSession(interview_id=content['itw_a'].id, user_id=world['eleve_3a'].id)
    db.session.add(session)
    db.session.flush()
    db.session.add(InterviewMessage(session_id=session.id, role='user', content='bonjour'))
    db.session.commit()


def gone(model, obj):
    from sqlalchemy import inspect
    return db.session.get(model, inspect(obj).identity[0]) is None  # obj may already be deleted


def test_admin_can_delete_user_who_took_an_interview(world, content, login):
    """Used to crash: interview sessions had no cascade and user_id is NOT NULL."""
    with_activity(world, content)
    login(world['dir_a']).post(f"/admin/user/{world['eleve_3a'].get_url_identifier()}/delete")
    assert gone(User, world['eleve_3a'])
    assert InterviewSession.query.count() == 0 and InterviewMessage.query.count() == 0


def test_confirmation_page_lists_what_goes(world, content, login):
    html = login(world['root']).get('/admin/tenants/lycee-a/delete').get_data(as_text=True)
    assert 'Lycee A' in html and 'confirm_name' in html


def test_delete_organization_with_its_content_and_own_accounts(world, content, login, no_backup):
    with_activity(world, content)
    resp = login(world['root']).post('/admin/tenants/lycee-a/delete',
                                     data={'confirm_name': 'Lycee A', 'delete_accounts': 'on'})
    assert resp.status_code == 302 and no_backup

    assert gone(Tenant, world['lycee_a'])
    assert gone(Group, world['g3a']) and gone(Group, world['g3b'])
    assert gone(Quiz, content['quiz_a']) and gone(Quiz, content['quiz_shared'])
    assert gone(Interview, content['itw_a'])
    for name in ('dir_a', 'prof_3a', 'prof_3b', 'eleve_3a', 'eleve_3a_3b'):
        assert gone(User, world[name]), name
    # Shared account kept, only detached; the other organization is untouched
    survivor = db.session.get(User, world['eleve_ab'].id)
    assert {g.name for g in survivor.groups} == {'2C'}
    assert survivor.responses.count() == 0  # their answers to lycee_a's quiz went with the quiz
    assert db.session.get(Quiz, content['quiz_b'].id) and db.session.get(Tenant, world['lycee_b'].id)
    assert db.session.get(User, world['root'].id)


def test_delete_organization_keeping_accounts(world, content, login, no_backup):
    login(world['root']).post('/admin/tenants/lycee-a/delete', data={'confirm_name': 'Lycee A'})
    assert gone(Tenant, world['lycee_a'])
    kept = db.session.get(User, world['eleve_3a'].id)
    assert kept is not None and kept.groups.count() == 0
    assert db.session.get(User, world['dir_a'].id).admin_tenant_ids() == set()


def test_wrong_name_deletes_nothing(world, content, login, no_backup):
    login(world['root']).post('/admin/tenants/lycee-a/delete', data={'confirm_name': 'lycee a', 'delete_accounts': 'on'})
    assert db.session.get(Tenant, world['lycee_a'].id) and not no_backup


def test_failed_backup_deletes_nothing(world, content, login, monkeypatch):
    monkeypatch.setattr(BackupManager, 'create_backup', lambda self: (False, None, 'mysqldump missing', 0))
    login(world['root']).post('/admin/tenants/lycee-a/delete', data={'confirm_name': 'Lycee A', 'delete_accounts': 'on'})
    assert db.session.get(Tenant, world['lycee_a'].id) and db.session.get(User, world['eleve_3a'].id)


def test_only_superadmin_deletes_organizations(world, login, no_backup):
    login(world['dir_a']).post('/admin/tenants/lycee-a/delete', data={'confirm_name': 'Lycee A'})
    assert db.session.get(Tenant, world['lycee_a'].id)


def test_list_offers_delete_even_with_groups(world, login):
    html = login(world['root']).get('/admin/tenants/list').get_data(as_text=True)
    assert '/admin/tenants/lycee-a/delete' in html
