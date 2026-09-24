"""Quiz images: access control, organization storage quota, images added while creating a quiz."""
import io
import os

import pytest

from app import db
from app.models import Quiz

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 100


@pytest.fixture
def uploads(app, tmp_path):
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    return tmp_path


def upload(client, quiz_ref, data=PNG):
    return client.post('/admin/quiz/upload-image', data={
        'quiz_id': str(quiz_ref), 'image': (io.BytesIO(data), 'a.png')}, content_type='multipart/form-data')


def test_upload_into_own_quiz(world, content, login, uploads):
    resp = upload(login(world['prof_3a']), content['quiz_a'].id)
    assert resp.status_code == 200
    assert os.listdir(uploads / f"quiz-{content['quiz_a'].id}") == [resp.get_json()['filename']]


@pytest.mark.parametrize('quiz_ref', ['../../../etc', 'x', '999999'])
def test_upload_rejects_forged_quiz_ids(world, login, uploads, quiz_ref):
    assert upload(login(world['prof_3a']), quiz_ref).status_code == 403
    assert not any(uploads.iterdir())


def test_upload_into_foreign_quiz_is_refused(world, content, login, uploads):
    assert upload(login(world['prof_3a']), content['quiz_b'].id).status_code == 403


def test_storage_quota(world, content, login, uploads):
    tenant = world['lycee_a']
    tenant.max_storage_mb = 1
    db.session.commit()
    folder = uploads / f"quiz-{content['quiz_a'].id}"
    folder.mkdir()
    (folder / 'big.png').write_bytes(b'\0' * (1024 * 1024 - 50))

    resp = upload(login(world['prof_3a']), content['quiz_a'].id)

    assert resp.status_code == 413
    assert tenant.get_usage_stats()['storage'] == {'current': 1.0, 'max': 1}


def test_images_added_while_creating_quiz_follow_the_quiz(world, login, uploads):
    client = login(world['prof_3a'])
    name = upload(client, 'temp').get_json()['filename']
    assert (uploads / f"quiz-tmp-{world['prof_3a'].id}" / name).exists()

    client.post('/admin/quiz/create', data={
        'markdown_content': f"# With image\n\n## QCM - Q ![image]({name}) [1 points]\n- [x] a\n- [ ] b\n",
        'group_ids': [world['g3a'].id]})

    quiz = Quiz.query.filter_by(title='With image').first()
    assert quiz is not None
    assert (uploads / f'quiz-{quiz.id}' / name).exists()
    assert not (uploads / f"quiz-tmp-{world['prof_3a'].id}" / name).exists()
