"""Single entry point for LLM access, provider-agnostic.

Two providers cover everything the app needs (text in, text out):
- 'anthropic' (default, recommended): native SDK, keeps prompt caching.
- 'openai_compatible': any server speaking the OpenAI Chat Completions API
  (OpenAI, Mistral, Gemini, OpenRouter, Groq, Ollama, vLLM...), chosen by
  its base URL.

Provider, base URL, key and model are read from SiteSettings on every call,
so a change made in the admin applies immediately in every worker without
restarting the containers. Environment variables are the fallback:
ANTHROPIC_API_KEY / CLAUDE_MODEL for Anthropic, AI_PROVIDER / AI_BASE_URL /
AI_API_KEY / AI_MODEL for the rest.
"""
import json
import re

from flask import current_app

ANTHROPIC = 'anthropic'
OPENAI_COMPATIBLE = 'openai_compatible'
PROVIDERS = (ANTHROPIC, OPENAI_COMPATIBLE)
DEFAULT_MODEL = 'claude-sonnet-4-20250514'  # Anthropic default when nothing is configured


class AIResponseError(Exception):
    """The LLM returned no usable text (refusal, filter, empty or truncated answer)."""


class AIConfigError(Exception):
    """The LLM provider is not configured (missing model, key or URL)."""


# ==================== Configuration ====================

def _settings():
    from app.models.settings import SiteSettings
    try:
        return SiteSettings.get_settings()
    except Exception:
        # Table missing (fresh DB before migrations) or DB unavailable
        return None


def get_config():
    """Effective {provider, base_url, api_key, model}: admin settings first, then env."""
    settings = _settings()
    env = current_app.config
    provider = (settings.ai_provider if settings and settings.ai_provider else None) \
        or env.get('AI_PROVIDER') or ANTHROPIC
    if provider not in PROVIDERS:
        provider = ANTHROPIC

    db_key = settings.get_ai_api_key() if settings else None
    db_model = settings.ai_model if settings else None
    if provider == ANTHROPIC:
        return {
            'provider': provider,
            'base_url': None,
            'api_key': db_key or env.get('ANTHROPIC_API_KEY'),
            'model': db_model or env.get('CLAUDE_MODEL') or DEFAULT_MODEL,
        }
    return {
        'provider': provider,
        'base_url': (settings.ai_base_url if settings and settings.ai_base_url else None) or env.get('AI_BASE_URL'),
        'api_key': db_key or env.get('AI_API_KEY'),
        'model': db_model or env.get('AI_MODEL'),
    }


def get_model():
    return get_config()['model']


def is_grok(provider, base_url, model):
    """xAI's Grok, directly or through an aggregator (e.g. OpenRouter's x-ai/grok-*)."""
    if provider != OPENAI_COMPATIBLE:
        return False
    return 'x.ai' in (base_url or '').lower() or 'grok' in (model or '').lower()


# ==================== Completion ====================

def complete(messages, system=None, max_tokens=4096, model=None):
    """Send a conversation and return the answer text.

    messages: [{'role': 'user'|'assistant', 'content': str or Anthropic text blocks}]
    system: str, or Anthropic text blocks (cache_control is kept for Anthropic,
            dropped for other providers).
    """
    config = get_config()
    model = model or config['model']
    if not model:
        raise AIConfigError('No AI model configured')
    if config['provider'] == ANTHROPIC:
        return _complete_anthropic(config, model, messages, system, max_tokens)
    return _complete_openai(config, model, messages, system, max_tokens)


def _complete_anthropic(config, model, messages, system, max_tokens):
    import anthropic
    client = anthropic.Anthropic(api_key=config['api_key'])
    kwargs = {'model': model, 'max_tokens': max_tokens, 'messages': messages}
    if system:
        kwargs['system'] = system
    message = client.messages.create(**kwargs)
    return extract_text(message)


def extract_text(message):
    """Concatenated text blocks of an Anthropic response.

    Recent models may start the content with thinking blocks, and a refusal
    comes back with an empty content list, so content[0].text is not safe.
    """
    if message.stop_reason == 'refusal':
        raise AIResponseError('The model declined the request')
    text = ''.join(block.text for block in message.content if block.type == 'text').strip()
    if not text:
        raise AIResponseError(f'Empty response (stop_reason={message.stop_reason})')
    return text


def _as_text(content):
    """Anthropic content (str or list of text blocks) as plain text."""
    if isinstance(content, str):
        return content
    return '\n'.join(block.get('text', '') for block in content if block.get('type') == 'text')


THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)


def _complete_openai(config, model, messages, system, max_tokens):
    import openai
    if not config['base_url']:
        raise AIConfigError('No base URL configured for the OpenAI-compatible provider')
    # Local servers (Ollama, vLLM) usually need no key, but the SDK wants a value
    client = openai.OpenAI(api_key=config['api_key'] or 'not-needed', base_url=config['base_url'])

    chat = [{'role': 'system', 'content': _as_text(system)}] if system else []
    chat += [{'role': m['role'], 'content': _as_text(m['content'])} for m in messages]

    try:
        response = client.chat.completions.create(model=model, messages=chat, max_tokens=max_tokens)
    except openai.BadRequestError as e:
        # OpenAI reasoning models only accept max_completion_tokens
        if 'max_completion_tokens' not in str(e):
            raise
        response = client.chat.completions.create(model=model, messages=chat, max_completion_tokens=max_tokens)

    if not response.choices:
        raise AIResponseError('Empty response (no choices)')
    choice = response.choices[0]
    if choice.finish_reason == 'content_filter':
        raise AIResponseError('The provider filtered the response')
    # Reasoning models served locally (Qwen, DeepSeek...) inline their reasoning
    text = THINK_RE.sub('', choice.message.content or '').strip()
    if not text:
        raise AIResponseError(f'Empty response (finish_reason={choice.finish_reason})')
    return text


def parse_json(text):
    """Parse a JSON object from an LLM answer: bare, fenced in ``` or surrounded by prose."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError('No JSON object found', text, 0)


# ==================== Admin helpers ====================

def list_models(provider=None, api_key=None, base_url=None):
    """Models available for a provider (typed values first, then the configured ones): [(id, name)]."""
    config = get_config()
    provider = provider or config['provider']
    if provider == OPENAI_COMPATIBLE and not base_url and provider == config['provider']:
        base_url = config['base_url']
    # Never send the saved key to another provider or another server
    same_endpoint = provider == config['provider'] and (provider == ANTHROPIC or base_url == config['base_url'])
    api_key = api_key or (config['api_key'] if same_endpoint else None)
    if provider == ANTHROPIC:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        return [(m.id, m.display_name) for m in client.models.list()]
    import openai
    if not base_url:
        raise AIConfigError('No base URL')
    client = openai.OpenAI(api_key=api_key or 'not-needed', base_url=base_url)
    return sorted((m.id, m.id) for m in client.models.list())
