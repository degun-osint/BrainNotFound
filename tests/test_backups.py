"""Backup files handling and restore safety (the MySQL part is covered by a manual e2e run)."""
import gzip
import io
import os
import tarfile

import pytest

from app import db
from app.models import User
from app.utils.backup_manager import BackupManager


def make_archive(path, sql):
    sql_gz = gzip.compress(sql)
    with tarfile.open(path, 'w:gz') as tar:
        info = tarfile.TarInfo('database.sql.gz')
        info.size = len(sql_gz)
        tar.addfile(info, io.BytesIO(sql_gz))


APP_DUMP = b'CREATE TABLE `groups` (\nCREATE TABLE `quizzes` (\nCREATE TABLE `users` (\n'


@pytest.fixture
def manager(app, tmp_path):
    app.config['BACKUP_LOCAL_DIR'] = str(tmp_path / 'backups')
    return BackupManager()


@pytest.mark.parametrize('name, valid', [
    ('backup_quizdb_20260101_010101.tar.gz', True),
    ('pre_restore_quizdb_20260101_010101-1.tar.gz', True),
    ('backup_old.sql.gz', True),
    ('../backup_x.tar.gz', False),
    ('backup_x.tar.gz/../../etc', False),
    ('evil.tar.gz', False),
])
def test_backup_names(name, valid):
    assert BackupManager.is_valid_backup_name(name) is valid


def test_check_backup_file_accepts_app_dump_only(manager, tmp_path):
    good, foreign, broken = tmp_path / 'good.tar.gz', tmp_path / 'foreign.tar.gz', tmp_path / 'broken.tar.gz'
    make_archive(good, APP_DUMP)
    make_archive(foreign, b'CREATE TABLE `wp_posts` (\n')
    broken.write_bytes(b'not a tarball')

    assert manager.check_backup_file(str(good)) is None
    assert 'not a backup of this application' in manager.check_backup_file(str(foreign))
    assert manager.check_backup_file(str(broken)) is not None


def test_same_second_backups_do_not_overwrite_each_other(manager, tmp_path):
    names = []
    for content in (b'first', b'second'):
        tmp = tmp_path / 'tmp'
        tmp.mkdir(exist_ok=True)
        path = tmp / 'backup_quizdb_20260101_010101.tar.gz'
        path.write_bytes(content)
        names.append(os.path.basename(manager.keep_locally(str(path), prefix='pre_restore_')))

    assert len(set(names)) == 2
    assert {open(manager.local_backup_path(n), 'rb').read() for n in names} == {b'first', b'second'}


def test_foreign_file_is_rejected_before_any_snapshot(manager, tmp_path, monkeypatch):
    foreign = tmp_path / 'foreign.tar.gz'
    make_archive(foreign, b'CREATE TABLE `wp_posts` (\n')
    monkeypatch.setattr(manager, 'create_backup', lambda: pytest.fail('snapshot should not be taken'))

    ok, message = manager.restore_backup(str(foreign))

    assert not ok and 'not a backup' in message


def test_failed_restore_rolls_back_to_snapshot(manager, tmp_path, monkeypatch):
    backup = tmp_path / 'backup.tar.gz'
    make_archive(backup, APP_DUMP)
    snapshot_src = tmp_path / 'snap' / 'backup_quizdb_20260101_010101.tar.gz'
    snapshot_src.parent.mkdir()
    snapshot_src.write_bytes(b'snapshot')
    monkeypatch.setattr(manager, 'create_backup', lambda: (True, str(snapshot_src), 'ok', 8))
    restored = []
    monkeypatch.setattr(manager, '_restore_file',
                        lambda path: restored.append(os.path.basename(path)) or (len(restored) > 1, 'boom'))

    ok, message = manager.restore_backup(str(backup))

    assert not ok and 'restored automatically' in message
    assert restored == ['backup.tar.gz', 'pre_restore_quizdb_20260101_010101.tar.gz']


# ==================== routes ====================

def test_restore_requires_typed_confirmation(world, login, manager, monkeypatch):
    monkeypatch.setattr(BackupManager, 'restore_backup', lambda *a, **k: pytest.fail('must not restore'))
    resp = login(world['root']).post('/admin/settings/restore-backup',
                                     json={'filename': 'backup_x.tar.gz', 'source': 'local', 'confirm': 'oui'})
    assert resp.status_code == 400


def test_restore_upload_checks_csrf_itself(app, world, login, monkeypatch):
    app.config['WTF_CSRF_ENABLED'] = True
    monkeypatch.setattr(BackupManager, 'restore_backup', lambda *a, **k: pytest.fail('must not restore'))
    resp = login(world['root']).post('/admin/settings/restore-upload', data={
        'confirm': 'RESTAURER', 'backup_file': (io.BytesIO(b'x'), 'b.tar.gz'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_backup_routes_are_superadmin_only(world, login):
    client = login(world['dir_a'])
    assert client.get('/admin/settings/backup-history').status_code == 302
    assert client.post('/admin/settings/restore-backup', json={}).status_code == 302


def test_backup_download_cannot_escape_folder(world, login, manager):
    client = login(world['root'])
    assert client.get('/admin/settings/backups/..%2Fconfig.py/download').status_code == 404


# ==================== sessions survive no id reuse ====================

def test_session_is_bound_to_uid_not_just_id(world, client):
    """After a restore rewinds auto-increments, an old cookie must not open someone else's account."""
    victim_id = world['eleve_3a'].id
    stale_session = world['eleve_3a'].get_id()
    db.session.delete(world['eleve_3a'])
    db.session.commit()
    newcomer = User(id=victim_id, username='newcomer', email='newcomer@test.local')
    newcomer.set_password('x')
    db.session.add(newcomer)
    db.session.commit()

    assert User.load_from_session_id(stale_session) is None
    assert User.load_from_session_id(str(victim_id)) is None  # legacy plain ids are refused
    assert User.load_from_session_id(newcomer.get_id()) == newcomer
