"""Server-side speech synthesis: configuration, audio route, cache and fallback."""
import time
from pathlib import Path

import pytest

from app import db
from app.models.interview import Interview, InterviewMessage, InterviewSession
from app.models.settings import SiteSettings
from app.utils import tts_cache, tts_client


@pytest.fixture
def cache_dir(app, tmp_path):
    """Keep generated audio out of the repository during tests."""
    app.config['TTS_CACHE_DIR'] = str(tmp_path / 'tts')
    return tmp_path / 'tts'


@pytest.fixture
def openai_provider(app):
    """A configured OpenAI-compatible provider (no network call is made)."""
    settings = SiteSettings.get_settings()
    settings.tts_provider = tts_client.OPENAI_COMPATIBLE
    settings.tts_base_url = 'https://api.openai.com/v1'
    settings.tts_model = 'gpt-4o-mini-tts'
    settings.tts_voice = 'nova'
    settings.set_tts_api_key('sk-test-key')
    db.session.commit()
    return settings


@pytest.fixture
def spoken(monkeypatch):
    """Record what would be sent to the provider, and hand back fake audio."""
    calls = []

    def fake(config, text, voice):
        calls.append({'text': text, 'voice': voice, 'model': config['model']})
        return b'ID3fake-mp3-bytes'

    monkeypatch.setattr(tts_client, '_synthesize_openai', fake)
    return calls


def session_with_reply(interview, user, content='Bonjour.'):
    s = InterviewSession(interview_id=interview.id, user_id=user.id)
    db.session.add(s)
    db.session.flush()
    message = InterviewMessage(session_id=s.id, role=InterviewMessage.ROLE_ASSISTANT, content=content)
    db.session.add(message)
    db.session.commit()
    return s, message


def audio_url(session, message):
    return f'/interview/session/{session.get_url_identifier()}/message/{message.id}/audio'


# ==================== Configuration ====================

def test_no_provider_by_default(app):
    assert tts_client.get_config()['provider'] == tts_client.NONE
    assert tts_client.is_enabled() is False


def test_admin_settings_win_over_the_environment(app, openai_provider):
    app.config['TTS_PROVIDER'] = tts_client.ELEVENLABS
    app.config['TTS_VOICE'] = 'from-env'
    config = tts_client.get_config()
    assert config['provider'] == tts_client.OPENAI_COMPATIBLE
    assert config['voice'] == 'nova'
    assert config['api_key'] == 'sk-test-key'
    assert tts_client.is_enabled() is True


def test_the_environment_is_the_fallback(app):
    app.config['TTS_PROVIDER'] = tts_client.OPENAI_COMPATIBLE
    app.config['TTS_BASE_URL'] = 'http://speech:8000/v1'
    app.config['TTS_MODEL'] = 'kokoro'
    config = tts_client.get_config()
    assert config['provider'] == tts_client.OPENAI_COMPATIBLE
    assert config['base_url'] == 'http://speech:8000/v1'
    assert config['model'] == 'kokoro'


def test_an_unknown_provider_falls_back_to_none(app):
    app.config['TTS_PROVIDER'] = 'robot-voice'
    assert tts_client.get_config()['provider'] == tts_client.NONE


def test_elevenlabs_without_a_key_is_not_enabled(app):
    settings = SiteSettings.get_settings()
    settings.tts_provider = tts_client.ELEVENLABS
    db.session.commit()
    assert tts_client.is_enabled() is False


def test_the_speech_key_is_stored_encrypted(app):
    settings = SiteSettings.get_settings()
    settings.set_tts_api_key('sk-secret')
    db.session.commit()
    assert 'sk-secret' not in (settings.tts_api_key_encrypted or '')
    assert settings.get_tts_api_key() == 'sk-secret'
    settings.set_tts_api_key('')
    assert settings.tts_api_key_encrypted is None


# ==================== Spoken text ====================

def test_staging_directions_are_not_read_aloud():
    assert tts_client.spoken_text('Bonjour.\n*elle consulte votre CV*\nParlez-moi de vous.') == \
        'Bonjour. Parlez-moi de vous.'


def test_a_long_reply_is_cut_on_a_sentence(app, openai_provider, spoken):
    long_text = ('Premiere phrase. ' * 300) + 'Fin.'
    tts_client.synthesize(long_text)
    sent = spoken[0]['text']
    assert len(sent) <= tts_client.MAX_CHARS
    assert sent.endswith('.') and 'Premiere phrase' in sent


def test_stripping_directions_is_idempotent():
    """synthesize() normalizes too, so a caller that already did it changes nothing."""
    once = tts_client.spoken_text('Bonjour.\n*sourit*\nAsseyez-vous.')
    assert tts_client.spoken_text(once) == once


def test_synthesize_never_sends_a_staging_direction(app, openai_provider, spoken):
    """Even called directly with a raw reply: nobody pays to have "sourit" read out."""
    tts_client.synthesize('Bonjour.\n*sourit*\nAsseyez-vous.')
    assert spoken[0]['text'] == 'Bonjour. Asseyez-vous.'


def test_nothing_to_read_is_an_error(app, openai_provider):
    with pytest.raises(tts_client.TTSError):
        tts_client.synthesize('   ')


def test_synthesis_without_a_provider_is_a_config_error(app):
    with pytest.raises(tts_client.TTSConfigError):
        tts_client.synthesize('Bonjour.')


# ==================== Cache ====================

def test_the_same_reply_is_paid_for_once(app, openai_provider, spoken, cache_dir):
    first = tts_cache.audio_path('Bonjour, asseyez-vous.')
    second = tts_cache.audio_path('Bonjour, asseyez-vous.')
    assert first == second
    assert first.read_bytes() == b'ID3fake-mp3-bytes'
    assert len(spoken) == 1  # the second call came from the cache


def test_the_voice_is_part_of_the_cache_key(app, openai_provider, spoken, cache_dir):
    one = tts_cache.audio_path('Bonjour.', voice='nova')
    two = tts_cache.audio_path('Bonjour.', voice='onyx')
    assert one != two
    assert [c['voice'] for c in spoken] == ['nova', 'onyx']


def test_only_the_spoken_text_matters_to_the_cache(app, openai_provider, spoken, cache_dir):
    """Directions become a pause, so replies that differ only by one sound identical."""
    first = tts_cache.audio_path('Bonjour.\n*sourit*\nAsseyez-vous.')
    second = tts_cache.audio_path('Bonjour.\n*fronce les sourcils*\nAsseyez-vous.')
    third = tts_cache.audio_path('Bonjour. Asseyez-vous.')

    assert first == second == third
    assert len(spoken) == 1 and spoken[0]['text'] == 'Bonjour. Asseyez-vous.'


def test_the_purge_drops_old_audio(app, openai_provider, spoken, cache_dir):
    path = tts_cache.audio_path('Bonjour.')
    app.config['TTS_CACHE_MAX_DAYS'] = 7
    old = time.time() - 8 * 86400
    import os
    os.utime(path, (old, old))

    removed, _ = tts_cache.purge_audio_cache()
    assert removed == 1
    assert not path.exists()


def test_the_purge_keeps_the_cache_under_its_ceiling(app, openai_provider, spoken, cache_dir):
    import os
    paths = [tts_cache.audio_path(f'Phrase numero {i}.') for i in range(5)]
    for age, path in enumerate(reversed(paths)):  # paths[-1] is the oldest touched
        stamp = time.time() - (age + 1) * 60
        os.utime(path, (stamp, stamp))

    app.config['TTS_CACHE_MAX_MB'] = 0  # everything is over the ceiling
    removed, _ = tts_cache.purge_audio_cache()
    assert removed == 5
    assert not any(p.exists() for p in paths)


def test_the_shipped_relative_cache_dir_resolves_absolutely(app, tmp_path, monkeypatch):
    """The bug: writing resolved 'tts_cache' against the working directory (/app),
    while send_file resolved it against app.root_path (/app/app). Every reply was
    synthesized, paid for, written in one place and looked for in another, then
    quietly replaced by the browser voice.
    """
    app.config['TTS_CACHE_DIR'] = 'tts_cache'   # the shipped default, relative
    monkeypatch.chdir(tmp_path)                 # a different cwd must not move the cache

    root = tts_cache.cache_root()

    assert root.is_absolute()
    assert root == Path(app.root_path).parent / 'tts_cache'
    assert root != Path(app.root_path) / 'tts_cache'   # not the package directory
    assert tts_cache.cache_root() == root              # and stable across calls


def test_an_absolute_cache_dir_is_left_alone(app, tmp_path):
    app.config['TTS_CACHE_DIR'] = str(tmp_path / 'ailleurs')
    assert tts_cache.cache_root() == tmp_path / 'ailleurs'


def test_the_writer_and_the_purge_use_the_same_directory(app, openai_provider, spoken, cache_dir):
    path = tts_cache.audio_path('Bonjour.')
    app.config['TTS_CACHE_MAX_MB'] = 0  # everything is over the ceiling

    removed, _ = tts_cache.purge_audio_cache()

    assert removed == 1 and not path.exists()


def test_the_purge_survives_a_missing_directory(app):
    app.config['TTS_CACHE_DIR'] = 'does/not/exist'
    assert tts_cache.purge_audio_cache() == (0, 0)


# ==================== Audio route ====================

def test_a_learner_gets_the_audio_of_their_own_reply(world, content, login, openai_provider, spoken, cache_dir):
    session, message = session_with_reply(content['itw_a'], world['eleve_3a'])
    response = login(world['eleve_3a']).get(audio_url(session, message))

    assert response.status_code == 200
    assert response.mimetype == 'audio/mpeg'
    assert response.data == b'ID3fake-mp3-bytes'
    assert 'private' in response.headers['Cache-Control']


def test_the_interview_voice_overrides_the_default(world, content, login, openai_provider, spoken, cache_dir):
    interview = content['itw_a']
    interview.tts_server_voice = 'onyx'
    session, message = session_with_reply(interview, world['eleve_3a'])

    login(world['eleve_3a']).get(audio_url(session, message))
    assert spoken[0]['voice'] == 'onyx'


def test_another_learner_cannot_fetch_the_audio(world, content, login, openai_provider, spoken, cache_dir):
    session, message = session_with_reply(content['itw_a'], world['eleve_3a'])
    assert login(world['eleve_3a_3b']).get(audio_url(session, message)).status_code == 403


def test_a_learner_message_has_no_audio(world, content, login, openai_provider, spoken, cache_dir):
    session, _ = session_with_reply(content['itw_a'], world['eleve_3a'])
    mine = InterviewMessage(session_id=session.id, role=InterviewMessage.ROLE_USER, content='Bonjour.')
    db.session.add(mine)
    db.session.commit()

    assert login(world['eleve_3a']).get(audio_url(session, mine)).status_code == 404


def test_audio_is_refused_when_the_interview_has_the_voice_off(world, content, login, openai_provider,
                                                              spoken, cache_dir):
    interview = content['itw_a']
    interview.tts_mode = Interview.TTS_OFF
    session, message = session_with_reply(interview, world['eleve_3a'])

    assert login(world['eleve_3a']).get(audio_url(session, message)).status_code == 404


def test_a_provider_failure_is_a_503_not_a_broken_interview(world, content, login, openai_provider,
                                                            monkeypatch, cache_dir):
    def boom(config, text, voice):
        raise tts_client.TTSError('provider is down')

    monkeypatch.setattr(tts_client, '_synthesize_openai', boom)
    session, message = session_with_reply(content['itw_a'], world['eleve_3a'])

    assert login(world['eleve_3a']).get(audio_url(session, message)).status_code == 503


def test_without_a_provider_the_route_says_so(world, content, login, cache_dir):
    session, message = session_with_reply(content['itw_a'], world['eleve_3a'])
    assert login(world['eleve_3a']).get(audio_url(session, message)).status_code == 503


# ==================== Admin: telling failures apart ====================

def refuse(status, body=None):
    """A provider answering with an HTTP error, as httpx reports it."""
    import httpx

    def raise_it(*args, **kwargs):
        request = httpx.Request('GET', 'https://api.elevenlabs.io/v1/voices')
        response = httpx.Response(status, request=request, json=body) if body is not None \
            else httpx.Response(status, request=request)
        raise httpx.HTTPStatusError(str(status), request=request, response=response)
    return raise_it


def list_voices(login, user, provider='elevenlabs'):
    return login(user).post('/admin/settings/tts-voices', json={'provider': provider}).get_json()


def test_a_refused_key_is_not_reported_as_unreachable(app, world, login, monkeypatch):
    """A 401 sent the admin looking for a network problem that did not exist."""
    monkeypatch.setattr(tts_client, 'list_voices', refuse(401))
    data = list_voices(login, world['root'])

    assert data['success'] is False
    assert '401' in data['message']
    assert 'refus' in data['message'].lower()
    assert 'joindre' not in data['message'].lower()


def test_the_provider_explanation_is_passed_through(app, world, login, monkeypatch):
    """ElevenLabs names the missing permission; that sentence is the useful part."""
    monkeypatch.setattr(tts_client, 'list_voices', refuse(401, {
        'detail': {'status': 'missing_permissions',
                   'message': 'The API key you used is missing the permission voices_read.'}}))
    message = list_voices(login, world['root'])['message']

    assert 'voices_read' in message
    assert '401' in message


def test_an_openai_style_error_body_is_read_too(app, world, login, monkeypatch):
    monkeypatch.setattr(tts_client, 'list_voices', refuse(403, {
        'error': {'message': 'Project does not have access to this model.'}}))
    assert 'does not have access' in list_voices(login, world['root'])['message']


def test_a_body_that_is_not_json_does_not_break_the_message(app, world, login, monkeypatch):
    monkeypatch.setattr(tts_client, 'list_voices', refuse(401))
    message = list_voices(login, world['root'])['message']
    assert '401' in message and 'refus' in message.lower()


def test_another_http_error_shows_its_status(app, world, login, monkeypatch):
    monkeypatch.setattr(tts_client, 'list_voices', refuse(429))
    assert '429' in list_voices(login, world['root'])['message']


def test_an_unreachable_provider_says_so(app, world, login, monkeypatch):
    import httpx

    def unreachable(*args, **kwargs):
        raise httpx.ConnectError('nope')

    monkeypatch.setattr(tts_client, 'list_voices', unreachable)
    assert 'joindre' in list_voices(login, world['root'])['message'].lower()


def test_a_missing_key_is_a_configuration_problem(app, world, login):
    # elevenlabs with nothing configured: TTSConfigError, not a network error
    message = list_voices(login, world['root'])['message'].lower()
    assert 'configuration' in message


def test_listing_voices_is_superadmin_only(app, world, login, openai_provider):
    assert login(world['dir_a']).post('/admin/settings/tts-voices', json={}).status_code in (302, 403)


# ==================== The chat chooses its source ====================

def chat_html(login, user, session):
    return login(user).get(f'/interview/session/{session.get_url_identifier()}/chat').get_data(as_text=True)


def test_the_chat_uses_the_browser_voice_without_a_provider(world, content, login):
    session, _ = session_with_reply(content['itw_a'], world['eleve_3a'])
    assert 'server: false' in chat_html(login, world['eleve_3a'], session)


def test_the_chat_prefers_the_server_voice_when_configured(world, content, login, openai_provider):
    session, _ = session_with_reply(content['itw_a'], world['eleve_3a'])
    html = chat_html(login, world['eleve_3a'], session)
    assert 'server: true' in html
    assert '/message/0/audio' in html  # the pattern the client fills with each message id


def test_has_server_voice_follows_the_interview_and_the_provider(app, world, content, openai_provider):
    from app.utils.interview_tasks import has_server_voice

    session = InterviewSession(interview_id=content['itw_a'].id, user_id=world['eleve_3a'].id)
    db.session.add(session)
    db.session.commit()
    assert has_server_voice(session) is True

    content['itw_a'].tts_mode = Interview.TTS_OFF
    assert has_server_voice(session) is False
