"""Single entry point for speech synthesis, provider-agnostic.

Same shape as ai_client: provider, base URL, key, model and voice are read from
SiteSettings on every call, so a change in the admin applies immediately in
every worker without restarting the containers. Environment variables are the
fallback: TTS_PROVIDER / TTS_BASE_URL / TTS_API_KEY / TTS_MODEL / TTS_VOICE.

Providers:
- 'none' (default): no server synthesis. The chat falls back to the voice of
  the learner's own browser, which costs nothing and needs no configuration.
- 'openai_compatible': any server speaking the OpenAI speech API
  (OpenAI, or a local server like Kokoro/openedai-speech), chosen by base URL.
- 'elevenlabs': best French voices, an order of magnitude more expensive.

Adding a provider means one _synthesize_* function and one VOICES entry.
"""
import re

from flask import current_app

from app.utils.ai_client import read_settings

NONE = 'none'
OPENAI_COMPATIBLE = 'openai_compatible'
ELEVENLABS = 'elevenlabs'
PROVIDERS = (NONE, OPENAI_COMPATIBLE, ELEVENLABS)

ELEVENLABS_URL = 'https://api.elevenlabs.io/v1'
DEFAULT_OPENAI_MODEL = 'gpt-4o-mini-tts'
DEFAULT_ELEVENLABS_MODEL = 'eleven_multilingual_v2'

# One reply at a time: OpenAI refuses past 4096, and a longer text means the
# persona is rambling, not that we should pay to read it out.
MAX_CHARS = 4000

AUDIO_MIME = 'audio/mpeg'
AUDIO_EXT = 'mp3'


class TTSConfigError(Exception):
    """No provider configured, or a required field is missing."""


class TTSError(Exception):
    """The provider returned no usable audio."""


# OpenAI publishes a fixed voice list (no endpoint for it); ElevenLabs has an API.
OPENAI_VOICES = ('alloy', 'ash', 'ballad', 'coral', 'echo', 'fable',
                 'nova', 'onyx', 'sage', 'shimmer', 'verse')


# ==================== Configuration ====================

def get_config():
    """Effective {provider, base_url, api_key, model, voice}: admin settings first, then env."""
    settings = read_settings()
    env = current_app.config

    provider = (settings.tts_provider if settings and settings.tts_provider else None) \
        or env.get('TTS_PROVIDER') or NONE
    if provider not in PROVIDERS:
        provider = NONE

    key = (settings.get_tts_api_key() if settings else None) or env.get('TTS_API_KEY')
    model = (settings.tts_model if settings and settings.tts_model else None) or env.get('TTS_MODEL')
    voice = (settings.tts_voice if settings and settings.tts_voice else None) or env.get('TTS_VOICE')

    if provider == ELEVENLABS:
        base_url = ELEVENLABS_URL
        model = model or DEFAULT_ELEVENLABS_MODEL
    else:
        base_url = (settings.tts_base_url if settings and settings.tts_base_url else None) \
            or env.get('TTS_BASE_URL')
        model = model or (DEFAULT_OPENAI_MODEL if provider == OPENAI_COMPATIBLE else None)

    return {'provider': provider, 'base_url': base_url, 'api_key': key,
            'model': model, 'voice': voice}


def is_enabled():
    """Whether server synthesis is configured at all (the chat asks before offering audio)."""
    try:
        config = get_config()
    except Exception:  # no app context, database down on a fresh install...
        return False
    if config['provider'] == NONE:
        return False
    if not config['api_key'] and config['provider'] == ELEVENLABS:
        return False
    return True


# ==================== Synthesis ====================

def synthesize(text, voice=None):
    """Speech for text, as MP3 bytes. Raises TTSConfigError / TTSError.

    voice: overrides the configured default (an interview can have its own).
    """
    config = get_config()
    if config['provider'] == NONE:
        raise TTSConfigError('No speech provider configured')

    # Normalized here and not only in the caller: every caller pays per character,
    # and nobody should ever hear a staging direction read out. Idempotent, so
    # text that already went through spoken_text() is unchanged.
    text = spoken_text(text)
    if not text:
        raise TTSError('Nothing to read')
    if len(text) > MAX_CHARS:
        text = _cut_on_sentence(text, MAX_CHARS)

    voice = (voice or config['voice'] or '').strip() or None
    if config['provider'] == ELEVENLABS:
        return _synthesize_elevenlabs(config, text, voice)
    return _synthesize_openai(config, text, voice)


def _cut_on_sentence(text, limit):
    """Trim to limit on the last sentence break, so audio never stops mid-word."""
    head = text[:limit]
    cut = max(head.rfind('. '), head.rfind('! '), head.rfind('? '), head.rfind('\n'))
    return head[:cut + 1].strip() if cut > limit // 2 else head.rsplit(' ', 1)[0]


def _synthesize_openai(config, text, voice):
    import openai
    if not config['base_url']:
        raise TTSConfigError('No base URL configured for the OpenAI-compatible provider')
    # Local servers usually need no key, but the SDK wants a value
    client = openai.OpenAI(api_key=config['api_key'] or 'not-needed', base_url=config['base_url'])
    try:
        response = client.audio.speech.create(
            model=config['model'],
            voice=voice or OPENAI_VOICES[0],
            input=text,
            response_format=AUDIO_EXT,
        )
    except openai.OpenAIError as e:
        raise TTSError(str(e)) from e
    audio = response.content
    if not audio:
        raise TTSError('Empty audio response')
    return audio


def _synthesize_elevenlabs(config, text, voice):
    import httpx
    if not config['api_key']:
        raise TTSConfigError('No API key configured for ElevenLabs')
    if not voice:
        raise TTSConfigError('ElevenLabs needs a voice id')
    try:
        response = httpx.post(
            f"{ELEVENLABS_URL}/text-to-speech/{voice}",
            headers={'xi-api-key': config['api_key'], 'accept': AUDIO_MIME},
            json={'text': text, 'model_id': config['model']},
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise TTSError(f'ElevenLabs returned {e.response.status_code}') from e
    except httpx.HTTPError as e:
        raise TTSError(str(e)) from e
    if not response.content:
        raise TTSError('Empty audio response')
    return response.content


# ==================== Spoken text ====================

ACTION_RE = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)')
DOTS_RE = re.compile(r'(\.\s*){2,}')


def spoken_text(text):
    """What a reply sounds like: staging directions become pauses, not words.

    Mirrors speakableText() in the chat template, so the browser fallback and
    the server read exactly the same thing.
    """
    spoken = ACTION_RE.sub('. ', text or '')
    spoken = re.sub(r'\s*\n+\s*', '. ', spoken)
    spoken = DOTS_RE.sub('. ', spoken)
    return re.sub(r'\s+', ' ', spoken).strip()


# ==================== Admin helpers ====================

def list_voices(provider=None, api_key=None, base_url=None):
    """Voices available for a provider: [(id, name)]. Also tests the key."""
    config = get_config()
    provider = provider or config['provider']
    if provider == OPENAI_COMPATIBLE:
        # Never send the saved key to another server
        same_endpoint = provider == config['provider'] and (base_url or config['base_url']) == config['base_url']
        key = api_key or (config['api_key'] if same_endpoint else None)
        url = base_url or config['base_url']
        if not url:
            raise TTSConfigError('No base URL')
        # A local server may expose its own voices; OpenAI itself does not
        try:
            import openai
            client = openai.OpenAI(api_key=key or 'not-needed', base_url=url)
            voices = [(v.id, v.id) for v in client.models.list() if 'tts' not in v.id]
        except Exception:
            voices = []
        return voices or [(v, v) for v in OPENAI_VOICES]
    if provider == ELEVENLABS:
        import httpx
        key = api_key or (config['api_key'] if provider == config['provider'] else None)
        if not key:
            raise TTSConfigError('No API key')
        response = httpx.get(f'{ELEVENLABS_URL}/voices', headers={'xi-api-key': key}, timeout=30)
        response.raise_for_status()
        return sorted((v['voice_id'], v.get('name') or v['voice_id'])
                      for v in response.json().get('voices', []))
    raise TTSConfigError('No speech provider configured')
