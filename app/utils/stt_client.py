"""Single entry point for speech recognition, provider-agnostic.

Same shape as ai_client and tts_client: provider, base URL, key and model are
read from SiteSettings on every call, so a change in the admin applies
immediately in every worker without restarting the containers. Environment
variables are the fallback: STT_PROVIDER / STT_BASE_URL / STT_API_KEY /
STT_MODEL.

Providers:
- 'none' (default): no speech recognition. The learner types, as before.
- 'openai_compatible': any server speaking the OpenAI transcription API
  (OpenAI Whisper, or a local faster-whisper / whisper.cpp server).
- 'elevenlabs': their Scribe models. NOT reachable through 'openai_compatible':
  /v1/audio/transcriptions does not exist there (404), the endpoint is
  /v1/speech-to-text, it authenticates with xi-api-key rather than a bearer
  token, and it wants model_id rather than model.

The audio itself is never stored. It is personal data the learner produced
here and now - unlike the audio of tts_cache, which is derived from a reply
already sitting in the database - so it is transcribed in memory and dropped.
Only the text reaches a disk, in the message the learner chooses to send.
"""
from flask import current_app

from app.utils.ai_client import read_settings

NONE = 'none'
OPENAI_COMPATIBLE = 'openai_compatible'
ELEVENLABS = 'elevenlabs'
PROVIDERS = (NONE, OPENAI_COMPATIBLE, ELEVENLABS)

DEFAULT_MODEL = 'whisper-1'
ELEVENLABS_URL = 'https://api.elevenlabs.io/v1'
# The API lists its own: 'scribe_v1', 'scribe_v1_experimental', 'scribe_v2',
# 'scribe_v2_medical'. v2 is the current default; the admin can change it.
DEFAULT_ELEVENLABS_MODEL = 'scribe_v2'

# A single learner answer. Whisper itself accepts 25 MB; this is about an answer
# that got out of hand (or a tab left recording), not about the API limit.
MAX_BYTES = 10 * 1024 * 1024
MAX_SECONDS = 180

# What MediaRecorder produces across browsers, and what the API accepts
ACCEPTED_TYPES = {
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/mp4': 'mp4',
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
}


class STTConfigError(Exception):
    """No provider configured, or a required field is missing."""


class STTError(Exception):
    """The provider returned no usable transcript."""


# ==================== Configuration ====================

def get_config():
    """Effective {provider, base_url, api_key, model}: admin settings first, then env."""
    settings = read_settings()
    env = current_app.config

    provider = (settings.stt_provider if settings and settings.stt_provider else None) \
        or env.get('STT_PROVIDER') or NONE
    if provider not in PROVIDERS:
        provider = NONE

    key = (settings.get_stt_api_key() if settings else None) or env.get('STT_API_KEY')
    model = (settings.stt_model if settings and settings.stt_model else None) or env.get('STT_MODEL')

    if provider == ELEVENLABS:
        # Fixed endpoint: there is nothing for an admin to get wrong here
        return {'provider': provider, 'base_url': ELEVENLABS_URL, 'api_key': key,
                'model': model or DEFAULT_ELEVENLABS_MODEL}

    return {
        'provider': provider,
        'base_url': (settings.stt_base_url if settings and settings.stt_base_url else None)
        or env.get('STT_BASE_URL'),
        'api_key': key,
        'model': model or DEFAULT_MODEL,
    }


def is_enabled():
    """Whether speech recognition is configured at all (the chat asks before offering a mic)."""
    try:
        config = get_config()
    except Exception:  # no app context, database down on a fresh install...
        return False
    if config['provider'] == NONE:
        return False
    if config['provider'] == ELEVENLABS:
        return bool(config['api_key'])   # the URL is fixed, the key is not
    return bool(config['base_url'])


def extension_for(content_type, filename=None):
    """File extension for a recording, or None if we don't accept it.

    MediaRecorder reports codecs too ("audio/webm;codecs=opus"), which the
    provider does not need and must not see in the filename.

    Some browsers hand over a blob with no usable type, which arrives as
    application/octet-stream and would be refused for no good reason. The
    filename the client sends carries the container too, so it is the fallback.
    """
    base = (content_type or '').split(';')[0].strip().lower()
    extension = ACCEPTED_TYPES.get(base)
    if extension:
        return extension
    suffix = (filename or '').rsplit('.', 1)[-1].strip().lower()
    return suffix if suffix in set(ACCEPTED_TYPES.values()) else None


# ==================== Transcription ====================

def transcribe(audio, content_type, lang='fr', filename=None):
    """Text spoken in audio (bytes). Raises STTConfigError / STTError.

    lang: ISO code passed to the provider; it markedly improves accuracy on
    short answers, where a model otherwise guesses the language from a few words.
    """
    config = get_config()
    if config['provider'] == NONE:
        raise STTConfigError('No speech recognition provider configured')
    if config['provider'] == OPENAI_COMPATIBLE and not config['base_url']:
        raise STTConfigError('No base URL configured for the transcription provider')
    if config['provider'] == ELEVENLABS and not config['api_key']:
        raise STTConfigError('No API key configured for ElevenLabs')

    extension = extension_for(content_type, filename)
    if not extension:
        raise STTError(f'Unsupported audio type: {content_type!r} (file {filename!r})')
    if not audio:
        raise STTError('Empty recording')
    if len(audio) > MAX_BYTES:
        raise STTError(f'Recording too large ({len(audio) // 1024} KiB)')

    base_type = content_type.split(';')[0]
    if base_type.lower() not in ACCEPTED_TYPES:
        base_type = next(t for t, e in ACCEPTED_TYPES.items() if e == extension)
    if config['provider'] == ELEVENLABS:
        return _transcribe_elevenlabs(config, audio, extension, base_type, lang)

    import openai
    client = openai.OpenAI(api_key=config['api_key'] or 'not-needed', base_url=config['base_url'])
    try:
        result = client.audio.transcriptions.create(
            model=config['model'],
            file=(f'answer.{extension}', audio, base_type),
            language=lang,
            response_format='text',
        )
    except openai.OpenAIError as e:
        raise STTError(str(e)) from e

    # response_format='text' gives a plain string; some servers still return an object
    text = (result if isinstance(result, str) else getattr(result, 'text', '')).strip()
    if not text:
        raise STTError('Nothing recognized in the recording')
    return text


def _transcribe_elevenlabs(config, audio, extension, base_type, lang):
    """Their Scribe endpoint: xi-api-key, model_id, and the text under 'text'."""
    import httpx

    try:
        response = httpx.post(
            f'{ELEVENLABS_URL}/speech-to-text',
            headers={'xi-api-key': config['api_key']},
            files={'file': (f'answer.{extension}', audio, base_type)},
            # language_code is the documented name; an unknown field is ignored
            # rather than refused, so a wrong guess costs the hint, not the call
            data={'model_id': config['model'], 'language_code': lang},
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise STTError(f'ElevenLabs returned {e.response.status_code}: '
                       f'{(e.response.text or "")[:200]}') from e
    except httpx.HTTPError as e:
        raise STTError(str(e)) from e

    try:
        text = (response.json().get('text') or '').strip()
    except ValueError as e:
        raise STTError('Unreadable answer from ElevenLabs') from e
    if not text:
        raise STTError('Nothing recognized in the recording')
    return text
