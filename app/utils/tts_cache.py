"""Disk cache for generated audio, keyed by what is said and by whom.

Audio is not user data: it is derived from a message that is already in the
database, and it regenerates on demand. So it is a cache, outside UPLOAD_FOLDER
and outside the backups, purged by the periodic tick.

Keying on the content means the same opening line, heard by thirty learners of
the same group, is paid for once; replaying a reply is free.
"""
import hashlib
import logging
import os
import time
from pathlib import Path

from flask import current_app

from app.utils import tts_client

logger = logging.getLogger(__name__)


def cache_root():
    """Absolute cache directory, whether TTS_CACHE_DIR is relative or not.

    A relative path cannot be left as is: writing resolves it against the current
    working directory (/app under gunicorn), while send_file resolves it against
    app.root_path - the package directory, /app/app. The audio was written in one
    place and looked for in another, and every reply fell back to the browser
    voice after being paid for. Anchored on the project root, which is what
    docker-compose bind-mounts as ./tts_cache.
    """
    configured = Path(current_app.config.get('TTS_CACHE_DIR', 'tts_cache'))
    if configured.is_absolute():
        return configured
    return Path(current_app.root_path).parent / configured


def cache_dir():
    """The cache directory, created on first use."""
    path = cache_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(text, voice, config):
    """Identify an audio file by everything that changes how it sounds."""
    seed = '|'.join((config['provider'], config['model'] or '', voice or '', text))
    return hashlib.sha256(seed.encode('utf-8')).hexdigest()


def audio_path(text, voice=None):
    """Path to the MP3 of text, generating it if the cache doesn't have it yet.

    Raises TTSConfigError / TTSError from tts_client: callers decide whether a
    missing voice is worth failing over (in the chat, it is not).
    """
    spoken = tts_client.spoken_text(text)
    if not spoken:
        raise tts_client.TTSError('Nothing to read')

    config = tts_client.get_config()
    if config['provider'] == tts_client.NONE:
        raise tts_client.TTSConfigError('No speech provider configured')
    voice = voice or config['voice']

    path = cache_dir() / f'{cache_key(spoken, voice, config)}.{tts_client.AUDIO_EXT}'
    if path.exists() and path.stat().st_size:
        os.utime(path, None)  # a replayed message stays in the cache longer
        return path

    audio = tts_client.synthesize(spoken, voice=voice)
    # Write beside the target then rename: a reader never sees a half-written file,
    # and two requests for the same reply can't interleave (same bytes either way).
    tmp = path.with_suffix(f'.{os.getpid()}.part')
    tmp.write_bytes(audio)
    tmp.replace(path)
    return path


def purge_audio_cache():
    """Drop audio older than TTS_CACHE_MAX_DAYS, then the oldest until under TTS_CACHE_MAX_MB."""
    directory = cache_root()  # same resolution as the writer, or it would purge nothing
    if not directory.is_dir():
        return 0, 0

    max_days = current_app.config.get('TTS_CACHE_MAX_DAYS', 30)
    max_bytes = current_app.config.get('TTS_CACHE_MAX_MB', 512) * 1024 * 1024
    cutoff = time.time() - max_days * 86400

    files, removed, freed = [], 0, 0
    for path in directory.glob(f'*.{tts_client.AUDIO_EXT}'):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            gone = _unlink(path, stat.st_size)
            freed += gone
            removed += 1 if gone else 0
        else:
            files.append((stat.st_mtime, stat.st_size, path))

    total = sum(size for _, size, _ in files)
    for _, size, path in sorted(files):  # oldest touched first
        if total <= max_bytes:
            break
        gone = _unlink(path, size)
        total -= gone
        freed += gone
        removed += 1 if gone else 0

    # Leftover .part files from a crashed write
    for path in directory.glob('*.part'):
        if path.stat().st_mtime < time.time() - 3600:
            _unlink(path, 0)

    if removed:
        logger.info(f'TTS cache: {removed} file(s) removed, {freed // 1024} KiB freed')
    return removed, freed


def _unlink(path, size):
    """Delete one cached file, returning the bytes freed (0 if it couldn't be removed)."""
    try:
        path.unlink()
        return size
    except OSError as e:
        logger.warning(f'TTS cache: could not remove {path.name}: {e}')
        return 0
