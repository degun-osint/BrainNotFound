"""Voice reading of interview replies (browser speech synthesis)."""
from app import db
from app.models.interview import Interview, InterviewSession


def session_for(interview, user, **kwargs):
    s = InterviewSession(interview_id=interview.id, user_id=user.id, **kwargs)
    db.session.add(s)
    db.session.commit()
    return s


def chat_page(login, user, session):
    return login(user).get(f'/interview/session/{session.get_url_identifier()}/chat').get_data(as_text=True)


def test_mode_decides_whether_the_voice_is_offered(world, content, login):
    interview, learner = content['itw_a'], world['eleve_3a']
    session = session_for(interview, learner)

    interview.tts_mode = Interview.TTS_OFF
    db.session.commit()
    assert 'id="voice-toggle"' not in chat_page(login, learner, session)

    interview.tts_mode = Interview.TTS_OPTIONAL
    db.session.commit()
    assert 'id="voice-toggle"' in chat_page(login, learner, session)


def test_optional_mode_follows_the_learner_preference(world, content, login):
    interview, learner = content['itw_a'], world['eleve_3a']
    interview.tts_mode = Interview.TTS_OPTIONAL
    session = session_for(interview, learner)

    learner.tts_enabled = False
    db.session.commit()
    assert 'startOn: false' in chat_page(login, learner, session)

    learner.tts_enabled = True
    db.session.commit()
    assert 'startOn: true' in chat_page(login, learner, session)


def test_always_mode_starts_on_and_is_not_saved_as_a_preference(world, content, login):
    interview, learner = content['itw_a'], world['eleve_3a']
    interview.tts_mode = Interview.TTS_ALWAYS
    learner.tts_enabled = False  # the interview decides, not the learner
    session = session_for(interview, learner)
    db.session.commit()

    html = chat_page(login, learner, session)
    assert 'startOn: true' in html and 'persist: false' in html


def test_the_toggle_is_remembered_across_devices(world, content, login):
    learner = world['eleve_3a']
    client = login(learner)

    assert client.post('/interview/preferences/voice', json={'enabled': True}).get_json() == {
        'success': True, 'enabled': True}
    assert learner.tts_enabled is True

    client.post('/interview/preferences/voice', json={'enabled': False})
    assert learner.tts_enabled is False


def test_the_toggle_needs_a_login(client):
    assert client.post('/interview/preferences/voice', json={'enabled': True}).status_code in (301, 302)


def test_voice_settings_survive_an_export_and_reimport(world, content, login):
    import io
    import json

    interview = content['itw_a']
    interview.tts_mode = Interview.TTS_ALWAYS
    interview.tts_voice_hint = 'Thomas'
    interview.tts_rate = 0.9
    db.session.commit()

    client = login(world['dir_a'])
    exported = client.get(f'/interview/admin/interviews/{interview.get_url_identifier()}/export-json').get_json()
    assert exported['tts_mode'] == 'always' and exported['tts_voice_hint'] == 'Thomas'
    assert exported['tts_rate'] == 0.9

    client.post('/interview/admin/interviews/import', data={
        'file': (io.BytesIO(json.dumps(exported).encode()), 'itw.json')
    }, content_type='multipart/form-data', follow_redirects=True)

    imported = Interview.query.filter(Interview.id != interview.id, Interview.title == interview.title).first()
    assert imported is not None
    assert imported.get_tts_mode() == 'always'
    assert imported.tts_voice_hint == 'Thomas'
    assert imported.get_tts_rate() == 0.9


def test_an_old_export_imports_as_optional(world, content, login):
    import io
    import json

    client = login(world['dir_a'])
    client.post('/interview/admin/interviews/import', data={
        'file': (io.BytesIO(json.dumps({
            'export_type': 'interview', 'title': 'Sans voix', 'system_prompt': 'p'
        }).encode()), 'old.json')
    }, content_type='multipart/form-data', follow_redirects=True)

    imported = Interview.query.filter_by(title='Sans voix').first()
    assert imported is not None
    assert imported.get_tts_mode() == Interview.TTS_OPTIONAL
    assert imported.get_tts_rate() == 1.0


def test_the_spoken_language_follows_the_interface_language(world, content, login):
    """get_locale() hands templates a plain string: 'fr'.language would silently be undefined."""
    interview, learner = content['itw_a'], world['eleve_3a']
    session = session_for(interview, learner)

    learner.language_preference = 'fr'
    db.session.commit()
    assert 'lang: "fr-FR"' in chat_page(login, learner, session)

    learner.language_preference = 'en'
    db.session.commit()
    assert 'lang: "en-US"' in chat_page(login, learner, session)


def test_the_persona_voice_and_rate_reach_the_page(world, content, login):
    interview, learner = content['itw_a'], world['eleve_3a']
    interview.tts_voice_hint = 'Thomas'
    interview.tts_rate = 0.8
    session = session_for(interview, learner)
    db.session.commit()

    html = chat_page(login, learner, session)
    assert 'hint: "Thomas"' in html and 'rate: 0.8' in html


def test_the_wizard_offers_one_voice_field_per_engine(world, content, login):
    """Two free-text fields meant guessing which one applied; now the engine is
    chosen explicitly and a single list follows it."""
    interview = content['itw_a']
    interview.tts_voice_hint = 'Thomas'
    interview.tts_server_voice = 'nova'
    db.session.commit()

    client = login(world['dir_a'])
    html = client.get(f'/interview/admin/interviews/{interview.get_url_identifier()}/edit').get_data(as_text=True)

    assert 'name="tts_source"' in html and 'name="tts_voice"' in html
    assert 'name="tts_voice_hint"' not in html      # replaced by the single list
    assert 'name="tts_server_voice"' not in html
    # Both saved choices travel to the page, so switching engine restores each
    assert 'data-browser-voice="Thomas"' in html
    assert 'data-provider-voice="nova"' in html


def test_the_engine_decides_which_voice_column_is_written(world, content, login):
    from app.routes.interview import apply_tts_settings

    interview = content['itw_a']
    interview.tts_voice_hint = 'Thomas'
    interview.tts_server_voice = 'nova'

    apply_tts_settings(interview, {'tts_source': 'browser', 'tts_voice': 'Amelie'})
    assert interview.tts_voice_hint == 'Amelie'
    assert interview.tts_server_voice == 'nova'     # the other choice is kept

    apply_tts_settings(interview, {'tts_source': 'provider', 'tts_voice': 'onyx'})
    assert interview.tts_server_voice == 'onyx'
    assert interview.tts_voice_hint == 'Amelie'
    assert interview.get_tts_voice() == 'onyx'      # the one in use


def test_an_unknown_engine_falls_back_to_the_provider(world, content, login):
    from app.routes.interview import apply_tts_settings

    interview = content['itw_a']
    apply_tts_settings(interview, {'tts_source': 'telepathie', 'tts_voice': 'x'})
    assert interview.get_tts_source() == Interview.TTS_SOURCE_PROVIDER
    assert interview.uses_provider_voice() is True


def test_a_browser_interview_ignores_a_configured_provider(world, content, login):
    """Choosing the browser engine keeps an interview free of charge on purpose."""
    from app.models.settings import SiteSettings
    from app.utils import tts_client

    settings = SiteSettings.get_settings()
    settings.tts_provider = tts_client.OPENAI_COMPATIBLE
    settings.tts_base_url = 'https://api.openai.com/v1'
    settings.set_tts_api_key('sk-test')

    interview, learner = content['itw_a'], world['eleve_3a']
    interview.tts_source = Interview.TTS_SOURCE_BROWSER
    session = session_for(interview, learner)

    assert 'server: false' in chat_page(login, learner, session)

    interview.tts_source = Interview.TTS_SOURCE_PROVIDER
    db.session.commit()
    assert 'server: true' in chat_page(login, learner, session)


def test_the_voice_list_route_is_open_to_interview_admins(world, content, login):
    """Voice names are not sensitive, and whoever writes an interview picks its voice."""
    data = login(world['prof_3a']).get('/interview/admin/interviews/provider-voices').get_json()
    assert data['configured'] is False and data['voices'] == []

    assert login(world['eleve_3a']).get(
        '/interview/admin/interviews/provider-voices').status_code in (302, 403)


def test_the_wizard_exposes_the_voice_settings(world, content, login):
    interview = content['itw_a']
    interview.tts_mode = Interview.TTS_ALWAYS
    interview.tts_voice_hint = 'Thomas'
    db.session.commit()

    client = login(world['dir_a'])
    for url in ('/interview/admin/interviews/create',
                f'/interview/admin/interviews/{interview.get_url_identifier()}/edit'):
        html = client.get(url).get_data(as_text=True)
        assert 'name="tts_mode"' in html and 'name="tts_rate"' in html, url
        assert 'name="tts_source"' in html and 'name="tts_voice"' in html, url
    assert 'data-browser-voice="Thomas"' in html  # the edit page carries the saved voice


def test_the_voice_settings_are_saved_from_the_wizard(world, content, login):
    interview = content['itw_a']
    client = login(world['dir_a'])
    client.post(f'/interview/admin/interviews/{interview.get_url_identifier()}/edit', data={
        'title': interview.title,
        'system_prompt': 'prompt',
        'tts_mode': 'always',
        'tts_source': 'browser',
        'tts_voice': 'Amelie',
        'tts_rate': '0.8',
    }, follow_redirects=True)

    assert interview.get_tts_mode() == Interview.TTS_ALWAYS
    assert interview.get_tts_source() == Interview.TTS_SOURCE_BROWSER
    assert interview.tts_voice_hint == 'Amelie'
    assert interview.get_tts_voice() == 'Amelie'
    assert interview.get_tts_rate() == 0.8


def test_the_rate_is_clamped_and_a_bad_mode_falls_back(world, content, login):
    from app.routes.interview import apply_tts_settings

    interview = content['itw_a']
    apply_tts_settings(interview, {'tts_mode': 'loud', 'tts_rate': '9', 'tts_voice_hint': '  '})
    assert interview.tts_mode == Interview.TTS_OPTIONAL
    assert interview.tts_rate == 1.5
    assert interview.tts_voice_hint is None

    apply_tts_settings(interview, {'tts_mode': 'off', 'tts_rate': 'vite'})
    assert interview.tts_mode == Interview.TTS_OFF
    assert interview.tts_rate == 1.0
    assert interview.tts_offered() is False
