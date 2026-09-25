"""Scheduled FTP backups: when the next one is due.

No scheduler to keep in sync with the settings: the periodic tick (app.tasks.tick,
every 5 minutes) calls run_backup_if_due(), which compares the last scheduled
slot with the last backup. Slots are in the server's local time (TZ).
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PERIODS = {'hourly': timedelta(hours=1), 'daily': timedelta(days=1), 'weekly': timedelta(days=7)}


def _schedule(settings):
    frequency = settings.backup_frequency if settings.backup_frequency in PERIODS else 'daily'
    hour = settings.backup_hour if settings.backup_hour is not None else 3  # 0 = midnight, not "unset"
    day = settings.backup_day if settings.backup_day is not None else 0     # 0 = Monday
    return frequency, hour, day


def last_slot(settings, now=None):
    """Most recent scheduled backup time <= now (aware, local time)."""
    now = now or datetime.now().astimezone()
    frequency, hour, day = _schedule(settings)
    if frequency == 'hourly':
        return now.replace(minute=0, second=0, microsecond=0)
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if frequency == 'weekly':
        slot -= timedelta(days=(now.weekday() - day) % 7)
    if slot > now:
        slot -= PERIODS[frequency]
    return slot


def next_slot(settings, now=None):
    """Next scheduled backup time (aware, local time)."""
    frequency, _, _ = _schedule(settings)
    return last_slot(settings, now) + PERIODS[frequency]


def backup_due(settings, now=None):
    """FTP backups on, and no backup since the last scheduled slot (a missed slot is caught up)."""
    if not settings.ftp_enabled:
        return False
    if settings.last_backup_at is None:
        return True
    last = settings.last_backup_at.replace(tzinfo=timezone.utc)  # stored as naive UTC
    return last < last_slot(settings, now)


def run_backup_if_due(now=None):
    """Run the scheduled backup if it is due. Needs an app context."""
    from app.models.settings import SiteSettings
    from app.utils.backup_manager import BackupManager

    settings = SiteSettings.get_settings()
    if not backup_due(settings, now):
        return False
    logger.info('Starting scheduled backup...')
    result = BackupManager(settings).run_backup()  # records last_backup_at, even on failure
    if result['success']:
        logger.info(f"Scheduled backup completed: {result['message']}")
    else:
        logger.error(f"Scheduled backup failed: {result['message']}")
    return True


def get_next_backup_time():
    """Next scheduled backup for the settings page, or None when FTP backups are off."""
    from app.models.settings import SiteSettings
    settings = SiteSettings.get_settings()
    if not settings.ftp_enabled:
        return None
    return next_slot(settings)
