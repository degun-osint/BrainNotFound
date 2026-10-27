"""Voice input: the learner dictates, the server transcribes, nothing is stored."""
import io

import pytest

from app import db
from app.models.interview import Interview, InterviewMessage, InterviewSession
from app.models.settings import SiteSettings
from app.utils import stt_client


@pytest.fixture
def whisper(app):
    """A configured transcription provider (no network call is made)."""
    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.OPENAI_COMPATIBLE
    settings.stt_base_url = 'https://api.openai.com/v1'
    settings.stt_model = 'whisper-1'
    settings.set_stt_api_key('sk-test-key')
    db.session.commit()
    return settings


@pytest.fixture
def heard(monkeypatch):
    """Record what would be sent to the provider, and hand back a transcript."""
    calls = []

    def fake(audio, content_type, lang='fr', filename=None):
        calls.append({'bytes': len(audio), 'type': content_type, 'lang': lang, 'file': filename})
        return "Bonjour, je m'appelle Camille."

    monkeypatch.setattr(stt_client, 'transcribe', fake)
    return calls


def dictating_session(interview, user, consented=True):
    interview.stt_mode = Interview.STT_OPTIONAL
    s = InterviewSession(interview_id=interview.id, user_id=user.id)
    db.session.add(s)
    db.session.flush()
    if consented:
        from datetime import datetime
        s.voice_consent_at = datetime.utcnow()
    db.session.commit()
    return s


def post_recording(client, session, data=b'fake-webm-bytes', mimetype='audio/webm'):
    return client.post(
        f'/interview/session/{session.get_url_identifier()}/transcribe',
        data={'audio': (io.BytesIO(data), 'answer.webm', mimetype)},
        content_type='multipart/form-data')


# ==================== Configuration ====================

def test_no_provider_by_default(app):
    assert stt_client.get_config()['provider'] == stt_client.NONE
    assert stt_client.is_enabled() is False


def test_admin_settings_win_over_the_environment(app, whisper):
    app.config['STT_MODEL'] = 'from-env'
    config = stt_client.get_config()
    assert config['provider'] == stt_client.OPENAI_COMPATIBLE
    assert config['model'] == 'whisper-1'
    assert config['api_key'] == 'sk-test-key'
    assert stt_client.is_enabled() is True


def test_a_provider_without_a_url_is_not_enabled(app):
    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.OPENAI_COMPATIBLE
    db.session.commit()
    assert stt_client.is_enabled() is False


def test_the_transcription_key_is_stored_encrypted(app):
    settings = SiteSettings.get_settings()
    settings.set_stt_api_key('sk-secret')
    db.session.commit()
    assert 'sk-secret' not in (settings.stt_api_key_encrypted or '')
    assert settings.get_stt_api_key() == 'sk-secret'


def test_recording_formats_are_filtered(app):
    assert stt_client.extension_for('audio/webm;codecs=opus') == 'webm'
    assert stt_client.extension_for('audio/mp4') == 'mp4'
    assert stt_client.extension_for('video/mp4') is None
    assert stt_client.extension_for('') is None


def test_a_blob_without_a_usable_type_falls_back_to_its_name(app):
    """Some browsers hand over application/octet-stream; the container is still
    in the filename, and refusing the recording for that would be gratuitous."""
    assert stt_client.extension_for('application/octet-stream', 'answer.webm') == 'webm'
    assert stt_client.extension_for('', 'answer.mp4') == 'mp4'
    assert stt_client.extension_for('application/octet-stream', 'answer.exe') is None
    assert stt_client.extension_for('application/octet-stream', 'answer') is None
    # A usable type always wins over the name
    assert stt_client.extension_for('audio/ogg', 'answer.webm') == 'ogg'


def test_the_announced_type_is_corrected_from_the_extension(app, monkeypatch):
    """A provider must not be told application/octet-stream."""
    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.ELEVENLABS
    settings.set_stt_api_key('sk-eleven')
    db.session.commit()

    import httpx
    sent = {}

    class Answer:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'text': 'Bonjour.'}

    monkeypatch.setattr(httpx, 'post', lambda url, **kw: (sent.update(kw), Answer())[1])
    stt_client.transcribe(b'audio', 'application/octet-stream', filename='answer.webm')

    assert sent['files']['file'] == ('answer.webm', b'audio', 'audio/webm')


def test_an_unsupported_or_oversized_recording_is_refused(app, whisper):
    with pytest.raises(stt_client.STTError):
        stt_client.transcribe(b'x', 'video/mp4')
    with pytest.raises(stt_client.STTError):
        stt_client.transcribe(b'', 'audio/webm')
    with pytest.raises(stt_client.STTError):
        stt_client.transcribe(b'x' * (stt_client.MAX_BYTES + 1), 'audio/webm')


def test_transcription_without_a_provider_is_a_config_error(app):
    with pytest.raises(stt_client.STTConfigError):
        stt_client.transcribe(b'x', 'audio/webm')


def test_elevenlabs_needs_no_url_but_needs_a_key(app):
    """Their endpoint is fixed; pointing an OpenAI-compatible provider at
    api.elevenlabs.io cannot work - /v1/audio/transcriptions is a 404 there."""
    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.ELEVENLABS
    db.session.commit()

    config = stt_client.get_config()
    assert config['base_url'] == stt_client.ELEVENLABS_URL
    assert config['model'] == 'scribe_v2'
    assert stt_client.is_enabled() is False   # no key yet

    settings.set_stt_api_key('sk-eleven')
    db.session.commit()
    assert stt_client.is_enabled() is True


def test_elevenlabs_without_a_key_is_a_config_error(app):
    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.ELEVENLABS
    db.session.commit()
    with pytest.raises(stt_client.STTConfigError):
        stt_client.transcribe(b'x', 'audio/webm')


def test_the_elevenlabs_request_shape(app, monkeypatch):
    """xi-api-key, model_id and the file, not the OpenAI bearer/model shape."""
    import httpx

    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.ELEVENLABS
    settings.set_stt_api_key('sk-eleven')
    db.session.commit()

    sent = {}

    class Answer:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'text': 'Bonjour.'}

    def fake_post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return Answer()

    monkeypatch.setattr(httpx, 'post', fake_post)
    assert stt_client.transcribe(b'audio', 'audio/webm;codecs=opus', lang='fr') == 'Bonjour.'

    assert sent['url'].endswith('/speech-to-text')
    assert sent['headers'] == {'xi-api-key': 'sk-eleven'}
    assert sent['data']['model_id'] == 'scribe_v2'
    assert sent['data']['language_code'] == 'fr'
    assert sent['files']['file'][0] == 'answer.webm'
    assert sent['files']['file'][2] == 'audio/webm'   # codecs stripped


def test_an_elevenlabs_refusal_carries_its_status(app, monkeypatch):
    import httpx

    settings = SiteSettings.get_settings()
    settings.stt_provider = stt_client.ELEVENLABS
    settings.set_stt_api_key('sk-eleven')
    db.session.commit()

    def refusing_post(url, **kwargs):
        request = httpx.Request('POST', url)
        response = httpx.Response(401, request=request, text='missing permission')
        raise httpx.HTTPStatusError('401', request=request, response=response)

    monkeypatch.setattr(httpx, 'post', refusing_post)
    with pytest.raises(stt_client.STTError) as caught:
        stt_client.transcribe(b'audio', 'audio/webm')
    assert '401' in str(caught.value) and 'missing permission' in str(caught.value)


# ==================== Consent ====================

def test_the_microphone_is_refused_without_consent(world, content, login, whisper, heard):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner, consented=False)

    response = post_recording(login(learner), session)

    assert response.status_code == 403
    assert heard == []  # nothing was sent anywhere


def test_consent_is_recorded_once_with_its_date(world, content, login, whisper):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner, consented=False)
    client = login(learner)
    url = f'/interview/session/{session.get_url_identifier()}/voice-consent'

    assert client.post(url).get_json()['success'] is True
    first = session.voice_consent_at
    assert first is not None

    client.post(url)
    assert session.voice_consent_at == first  # not refreshed on every click


def test_consent_is_refused_when_the_interview_does_not_offer_dictation(world, content, login, whisper):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner, consented=False)
    content['itw_a'].stt_mode = Interview.STT_OFF
    db.session.commit()

    url = f'/interview/session/{session.get_url_identifier()}/voice-consent'
    assert login(learner).post(url).status_code == 404


# ==================== Transcription route ====================

def test_a_recording_comes_back_as_text_to_check(world, content, login, whisper, heard):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)

    data = post_recording(login(learner), session).get_json()

    assert data['text'] == "Bonjour, je m'appelle Camille."
    assert heard[0]['type'] == 'audio/webm'
    assert heard[0]['bytes'] == len(b'fake-webm-bytes')


def test_no_message_is_created_by_transcribing(world, content, login, whisper, heard):
    """The text lands in the input box: the learner reads it and decides."""
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)

    post_recording(login(learner), session)

    assert InterviewMessage.query.filter_by(session_id=session.id).count() == 0
    assert session.interaction_count == 0


def test_another_learner_cannot_post_a_recording(world, content, login, whisper, heard):
    session = dictating_session(content['itw_a'], world['eleve_3a'])
    assert post_recording(login(world['eleve_3a_3b']), session).status_code == 403


def test_a_finished_session_takes_no_more_recordings(world, content, login, whisper, heard):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)
    session.status = InterviewSession.STATUS_COMPLETED
    db.session.commit()

    assert post_recording(login(learner), session).status_code == 400


def test_an_interview_without_dictation_refuses(world, content, login, whisper, heard):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)
    content['itw_a'].stt_mode = Interview.STT_OFF
    db.session.commit()

    assert post_recording(login(learner), session).status_code == 404


def test_a_missing_recording_is_a_bad_request(world, content, login, whisper, heard):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)
    url = f'/interview/session/{session.get_url_identifier()}/transcribe'

    assert login(learner).post(url, data={}, content_type='multipart/form-data').status_code == 400


def test_an_unconfigured_provider_answers_503(world, content, login):
    """No `heard` fixture here: the real transcribe() must raise STTConfigError."""
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)
    assert post_recording(login(learner), session).status_code == 503


def test_an_unrecognized_recording_tells_the_learner_to_type(world, content, login, whisper, monkeypatch):
    def nothing_heard(audio, content_type, lang='fr', filename=None):
        raise stt_client.STTError('Nothing recognized in the recording')

    monkeypatch.setattr(stt_client, 'transcribe', nothing_heard)
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)

    response = post_recording(login(learner), session)
    assert response.status_code == 422
    assert 'tapez' in response.get_json()['error'].lower()


# ==================== The chat offers it, or does not ====================

def chat_html(login, user, session):
    return login(user).get(f'/interview/session/{session.get_url_identifier()}/chat').get_data(as_text=True)


def test_the_chat_offers_no_microphone_without_a_provider(world, content, login):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner)
    html = chat_html(login, learner, session)

    assert 'offered: false' in html
    assert 'id="mic-btn"' not in html


def test_the_chat_offers_the_microphone_when_configured(world, content, login, whisper):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner, consented=False)
    html = chat_html(login, learner, session)

    assert 'offered: true' in html
    assert 'consented: false' in html
    assert 'id="mic-btn"' in html
    assert 'id="consent-panel"' in html


def test_a_granted_consent_is_not_asked_again(world, content, login, whisper):
    learner = world['eleve_3a']
    session = dictating_session(content['itw_a'], learner, consented=True)
    assert 'consented: true' in chat_html(login, learner, session)


# ==================== Dictated answers are traceable ====================

def test_a_dictated_answer_is_marked_as_such(app, world, content, monkeypatch):
    """The flag travels from the browser to the stored message."""
    from app.utils import interview_tasks

    interview, learner = content['itw_a'], world['eleve_3a']
    session = dictating_session(interview, learner)
    monkeypatch.setattr(interview_tasks.ClaudeInterviewer, 'get_response',
                        lambda self, s, c: {'content': 'Et ensuite ?', 'end_signal': False})

    interview_tasks.process_interview_message_async(
        app, session.id, 'Bonjour, je dicte.', f'interview_{session.id}', from_voice=True)

    answer = InterviewMessage.query.filter_by(session_id=session.id,
                                              role=InterviewMessage.ROLE_USER).first()
    assert answer.from_voice is True


def test_a_typed_answer_is_not_marked(app, world, content, monkeypatch):
    from app.utils import interview_tasks

    interview, learner = content['itw_a'], world['eleve_3a']
    session = dictating_session(interview, learner)
    monkeypatch.setattr(interview_tasks.ClaudeInterviewer, 'get_response',
                        lambda self, s, c: {'content': 'Et ensuite ?', 'end_signal': False})

    interview_tasks.process_interview_message_async(
        app, session.id, 'Bonjour, je tape.', f'interview_{session.id}')

    answer = InterviewMessage.query.filter_by(session_id=session.id,
                                              role=InterviewMessage.ROLE_USER).first()
    assert not answer.from_voice


def test_the_wizard_warns_when_no_provider_is_configured(world, content, login):
    """Ticking the box without a provider would do nothing, silently."""
    url = f"/interview/admin/interviews/{content['itw_a'].get_url_identifier()}/edit"
    html = login(world['root']).get(url).get_data(as_text=True)

    assert 'name="stt_mode"' in html
    assert "Aucun fournisseur de transcription n'est configure" in html


def test_the_warning_goes_away_once_a_provider_exists(world, content, login, whisper):
    url = f"/interview/admin/interviews/{content['itw_a'].get_url_identifier()}/edit"
    html = login(world['root']).get(url).get_data(as_text=True)

    assert "Aucun fournisseur de transcription n'est configure" not in html


def test_an_instructor_is_told_to_ask_a_site_admin(world, content, login):
    """A group admin cannot open the site settings, so pointing them there is useless."""
    url = f"/interview/admin/interviews/{content['itw_a'].get_url_identifier()}/edit"
    html = login(world['prof_3a']).get(url).get_data(as_text=True)

    assert 'administrateur du site' in html
    assert 'Configurer maintenant' not in html


def test_the_dictation_setting_survives_an_export_and_reimport(world, content, login):
    import json

    interview = content['itw_a']
    interview.stt_mode = Interview.STT_OPTIONAL
    db.session.commit()

    client = login(world['dir_a'])
    exported = client.get(
        f'/interview/admin/interviews/{interview.get_url_identifier()}/export-json').get_json()
    assert exported['stt_mode'] == 'optional'

    client.post('/interview/admin/interviews/import', data={
        'file': (io.BytesIO(json.dumps(exported).encode()), 'itw.json')
    }, content_type='multipart/form-data', follow_redirects=True)

    imported = Interview.query.filter(Interview.id != interview.id,
                                      Interview.title == interview.title).first()
    assert imported.get_stt_mode() == Interview.STT_OPTIONAL


def test_an_old_export_imports_without_dictation(world, content, login):
    import json

    client = login(world['dir_a'])
    client.post('/interview/admin/interviews/import', data={
        'file': (io.BytesIO(json.dumps({
            'export_type': 'interview', 'title': 'Sans dictee', 'system_prompt': 'p'
        }).encode()), 'old.json')
    }, content_type='multipart/form-data', follow_redirects=True)

    imported = Interview.query.filter_by(title='Sans dictee').first()
    assert imported.get_stt_mode() == Interview.STT_OFF
    assert imported.stt_offered() is False
