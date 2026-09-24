"""LLM configuration from admin settings, providers and response parsing."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from app import db
from app.models import SiteSettings
from app.utils import ai_client


def block(type_, text=''):
    return SimpleNamespace(type=type_, text=text)


# ==================== fake OpenAI-compatible server ====================

class FakeOpenAI(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeOpenAI.requests.append(('GET', self.path, self.headers.get('Authorization'), None))
        if self.path.endswith('/models'):
            self._send(200, {'object': 'list', 'data': [
                {'id': 'mistral-large', 'object': 'model', 'created': 0, 'owned_by': 'x'},
                {'id': 'reasoner', 'object': 'model', 'created': 0, 'owned_by': 'x'},
            ]})
        else:
            self._send(404, {'error': {'message': 'not found'}})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        FakeOpenAI.requests.append(('POST', self.path, self.headers.get('Authorization'), body))
        if body['model'] == 'reasoner' and 'max_tokens' in body:
            return self._send(400, {'error': {'message': "Unsupported parameter: 'max_tokens'. "
                                                         "Use 'max_completion_tokens' instead.",
                                              'type': 'invalid_request_error'}})
        content = '<think>hmm</think>{"score": 1.5, "feedback": "ok"}'
        self._send(200, {'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': body['model'],
                         'choices': [{'index': 0, 'finish_reason': 'stop',
                                      'message': {'role': 'assistant', 'content': content}}]})


@pytest.fixture
def fake_server():
    FakeOpenAI.requests = []
    server = HTTPServer(('127.0.0.1', 0), FakeOpenAI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/v1'
    server.shutdown()


def use_openai_compatible(base_url, model='mistral-large', key='sk-mistral-1234'):
    settings = SiteSettings.get_settings()
    settings.ai_provider = ai_client.OPENAI_COMPATIBLE
    settings.ai_base_url = base_url
    settings.ai_model = model
    settings.set_ai_api_key(key)
    db.session.commit()


# ==================== configuration ====================

def test_env_is_used_when_nothing_is_set(app):
    app.config['ANTHROPIC_API_KEY'] = 'env-key'
    app.config['CLAUDE_MODEL'] = 'env-model'
    config = ai_client.get_config()
    assert (config['provider'], config['api_key'], config['model']) == ('anthropic', 'env-key', 'env-model')


def test_admin_settings_override_env_without_restart(app):
    app.config['ANTHROPIC_API_KEY'] = 'env-key'
    settings = SiteSettings.get_settings()
    settings.set_ai_api_key('sk-ant-admin-1234')
    settings.ai_model = 'admin-model'
    db.session.commit()

    assert ai_client.get_config()['api_key'] == 'sk-ant-admin-1234'
    assert ai_client.get_model() == 'admin-model'
    assert 'sk-ant' not in settings.ai_api_key_encrypted


def test_anthropic_env_key_is_never_used_for_another_provider(app):
    app.config['ANTHROPIC_API_KEY'] = 'sk-ant-env'
    settings = SiteSettings.get_settings()
    settings.ai_provider = ai_client.OPENAI_COMPATIBLE
    settings.ai_base_url = 'http://ollama:11434/v1'
    db.session.commit()
    assert ai_client.get_config()['api_key'] is None


@pytest.mark.parametrize('provider, base_url, model, expected', [
    ('openai_compatible', 'https://api.x.ai/v1', 'whatever', True),
    ('openai_compatible', 'https://openrouter.ai/api/v1', 'x-ai/grok-4', True),
    ('openai_compatible', 'https://api.mistral.ai/v1', 'mistral-large', False),
    ('anthropic', None, 'claude-x', False),
])
def test_is_grok(provider, base_url, model, expected):
    assert ai_client.is_grok(provider, base_url, model) is expected


# ==================== OpenAI-compatible provider ====================

def test_openai_compatible_completion(app, fake_server):
    use_openai_compatible(fake_server)

    text = ai_client.complete(
        [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi', 'cache_control': {'type': 'ephemeral'}}]}],
        system=[{'type': 'text', 'text': 'be nice', 'cache_control': {'type': 'ephemeral'}}],
    )

    assert text == '{"score": 1.5, "feedback": "ok"}'  # <think> stripped
    _, path, auth, body = FakeOpenAI.requests[-1]
    assert path == '/v1/chat/completions' and auth == 'Bearer sk-mistral-1234'
    assert body['messages'] == [{'role': 'system', 'content': 'be nice'}, {'role': 'user', 'content': 'hi'}]


def test_reasoning_models_get_max_completion_tokens(app, fake_server):
    use_openai_compatible(fake_server, model='reasoner')
    ai_client.complete([{'role': 'user', 'content': 'hi'}], max_tokens=123)
    assert FakeOpenAI.requests[-1][3]['max_completion_tokens'] == 123


def test_grader_works_with_another_provider(app, fake_server):
    from app.utils.claude_grader import grade_open_question
    use_openai_compatible(fake_server)
    result = grade_open_question('Q?', 'A', 'A', 2)
    assert result == {'score': 1.5, 'feedback': 'ok'}


def test_list_models_never_sends_saved_key_to_another_server(app, fake_server):
    use_openai_compatible('https://api.mistral.ai/v1', key='sk-mistral-secret')
    ai_client.list_models(ai_client.OPENAI_COMPATIBLE, None, fake_server)
    assert FakeOpenAI.requests[-1][2] == 'Bearer not-needed'


# ==================== parsing ====================

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


@pytest.mark.parametrize('text', [
    '{"score": 2}',
    '```json\n{"score": 2}\n```',
    'Voici mon evaluation :\n{"score": 2}\nBonne journee',
])
def test_parse_json_tolerates_chatty_models(text):
    assert ai_client.parse_json(text) == {'score': 2}


# ==================== settings page ====================

def save(client, **fields):
    data = {'action': 'save', 'site_title': 'T', 'ai_provider': 'anthropic'}
    data.update(fields)
    return client.post('/admin/settings', data=data)


def test_settings_save_key_encrypted_and_never_display_it(app, world, login, monkeypatch):
    from app.routes import admin
    monkeypatch.setattr(admin, 'check_ai_model', lambda *a, **k: None)
    client = login(world['root'])

    save(client, ai_api_key='sk-ant-secret-9876', ai_model='some-model')
    html = client.get('/admin/settings').get_data(as_text=True)

    settings = SiteSettings.get_settings()
    assert settings.get_ai_api_key() == 'sk-ant-secret-9876'
    assert settings.ai_model == 'some-model'
    assert 'sk-ant-secret' not in html and '...9876' in html


def test_switching_provider_drops_the_saved_key(app, world, login, monkeypatch):
    from app.routes import admin
    monkeypatch.setattr(admin, 'check_ai_model', lambda *a, **k: None)
    client = login(world['root'])
    save(client, ai_api_key='sk-ant-secret-9876')

    save(client, ai_provider='openai_compatible', ai_base_url='http://ollama:11434/v1', ai_model='llama3')

    settings = SiteSettings.get_settings()
    assert settings.ai_provider == 'openai_compatible'
    assert settings.get_ai_api_key() is None


def test_grok_requires_confirmation(app, world, login, monkeypatch):
    from app.routes import admin
    monkeypatch.setattr(admin, 'check_ai_model', lambda *a, **k: None)
    client = login(world['root'])
    grok = dict(ai_provider='openai_compatible', ai_base_url='https://api.x.ai/v1', ai_model='grok-4')

    save(client, **grok)
    assert SiteSettings.get_settings().ai_provider is None

    save(client, grok_confirmed='1', **grok)
    assert SiteSettings.get_settings().ai_model == 'grok-4'


def test_unknown_model_is_not_saved(app, world, login, fake_server):
    save(login(world['root']), ai_provider='openai_compatible', ai_base_url=fake_server, ai_model='typo-model')
    assert SiteSettings.get_settings().ai_model is None


def test_models_endpoint_lists_provider_models(app, world, login, fake_server):
    resp = login(world['root']).post('/admin/settings/ai-models', json={
        'provider': 'openai_compatible', 'base_url': fake_server, 'api_key': 'k'})
    assert [m['id'] for m in resp.get_json()['models']] == ['mistral-large', 'reasoner']


def test_settings_restricted_to_superadmin(world, login):
    assert login(world['dir_a']).get('/admin/settings').status_code == 302


def test_anthropic_path_keeps_prompt_caching(app, monkeypatch):
    import anthropic
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(stop_reason='end_turn', content=[block('text', 'bonjour')])

    monkeypatch.setattr(anthropic, 'Anthropic', lambda api_key=None: SimpleNamespace(messages=FakeMessages()))
    system = [{'type': 'text', 'text': 'sys', 'cache_control': {'type': 'ephemeral'}}]

    assert ai_client.complete([{'role': 'user', 'content': 'hi'}], system=system) == 'bonjour'
    assert calls[0]['system'] == system
