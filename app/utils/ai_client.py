"""Single entry point for Claude API access.

The API key and model are read from SiteSettings on every call, so a change
made in the admin settings applies immediately in every worker, without
restarting the containers. Environment variables (ANTHROPIC_API_KEY,
CLAUDE_MODEL) are the fallback when nothing is set in the admin.
"""
import anthropic
from flask import current_app

DEFAULT_MODEL = 'claude-sonnet-4-20250514'


class AIResponseError(Exception):
    """Claude returned no usable text (refusal, empty or truncated answer)."""


def _settings():
    from app.models.settings import SiteSettings
    try:
        return SiteSettings.get_settings()
    except Exception:
        # Table missing (fresh DB before migrations) or DB unavailable
        return None


def get_api_key():
    settings = _settings()
    key = settings.get_anthropic_api_key() if settings else None
    return key or current_app.config.get('ANTHROPIC_API_KEY')


def get_model():
    settings = _settings()
    if settings and settings.claude_model:
        return settings.claude_model
    return current_app.config.get('CLAUDE_MODEL') or DEFAULT_MODEL


def get_client(api_key=None):
    return anthropic.Anthropic(api_key=api_key or get_api_key())


def extract_text(message):
    """Concatenated text blocks of a response.

    Recent models may start the content with thinking blocks, and a refusal
    comes back with an empty content list, so content[0].text is not safe.
    """
    if message.stop_reason == 'refusal':
        raise AIResponseError('Claude declined the request')
    text = ''.join(block.text for block in message.content if block.type == 'text').strip()
    if not text:
        raise AIResponseError(f'Empty response (stop_reason={message.stop_reason})')
    return text


def list_models(api_key=None):
    """Models available with the given (or configured) key, newest first: [(id, display_name)]."""
    client = get_client(api_key)
    return [(m.id, m.display_name) for m in client.models.list()]
