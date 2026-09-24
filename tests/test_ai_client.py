"""Claude configuration from admin settings and response parsing."""
from types import SimpleNamespace

import pytest

from app import db
from app.models import SiteSettings
from app.utils import ai_client


def block(type_, text=''):
    return SimpleNamespace(type=type_, text=text)


def test_env_is_used_when_nothing_is_set(app):
    app.config['ANTHROPIC_API_KEY'] = 'env-key'
    app.config['CLAUDE_MODEL'] = 'env-model'
    assert ai_client.get_api_key() == 'env-key'
    assert ai_client.get_model() == 'env-model'


def test_admin_settings_override_env_without_restart(app):
    app.config['ANTHROPIC_API_KEY'] = 'env-key'
    settings = SiteSettings.get_settings()
    settings.set_anthropic_api_key('sk-ant-admin-1234')
    settings.claude_model = 'admin-model'
    db.session.commit()

    assert ai_client.get_api_key() == 'sk-ant-admin-1234'
    assert ai_client.get_model() == 'admin-model'
    assert 'sk-ant' not in settings.anthropic_api_key_encrypted


def test_extract_text_skips_thinking_blocks():
    message = SimpleNamespace(stop_reason='end_turn',
                              content=[block('thinking'), block('text', ' {"score": 1} ')])
    assert ai_client.extract_text(message) == '{"score": 1}'


@pytest.mark.parametrize('message', [
    SimpleNamespace(stop_reason='refusal', content=[]),
    SimpleNamespace(stop_reason='max_tokens', content=[block('thinking')]),
])
def test_extract_text_raises_on_unusable_response(message):
    with pytest.raises(ai_client.AIResponseError):
        ai_client.extract_text(message)


def test_settings_page_saves_key_encrypted_and_never_displays_it(app, world, login, monkeypatch):
    from app.routes import admin
    monkeypatch.setattr(admin, 'check_claude_model', lambda model, key=None: None)
    client = login(world['root'])

    client.post('/admin/settings', data={
        'action': 'save', 'site_title': 'T', 'anthropic_api_key': 'sk-ant-secret-9876',
        'claude_model': 'some-model',
    })
    html = client.get('/admin/settings').get_data(as_text=True)

    settings = SiteSettings.get_settings()
    assert settings.get_anthropic_api_key() == 'sk-ant-secret-9876'
    assert settings.claude_model == 'some-model'
    assert 'sk-ant-secret' not in html and '...9876' in html


def test_unknown_model_is_not_saved(app, world, login, monkeypatch):
    from app.routes import admin
    monkeypatch.setattr(admin, 'check_claude_model', lambda model, key=None: 'unknown')
    login(world['root']).post('/admin/settings', data={
        'action': 'save', 'site_title': 'T', 'claude_model': 'claude-typo',
    })
    assert SiteSettings.get_settings().claude_model is None


def test_settings_restricted_to_superadmin(world, login):
    resp = login(world['dir_a']).get('/admin/settings')
    assert resp.status_code == 302
