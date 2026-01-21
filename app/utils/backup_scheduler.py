"""Backup scheduler using APScheduler."""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def run_scheduled_backup():
    """Execute backup within app context."""
    from flask import current_app
    from app import db
    from app.models.settings import SiteSettings
    from app.utils.backup_manager import BackupManager

    try:
        # Check if backup is enabled
        settings = SiteSettings.get_settings()
        if not settings.ftp_enabled:
            logger.info("Scheduled backup skipped: FTP not enabled")
            return

        logger.info("Starting scheduled backup...")
        manager = BackupManager(settings)
        result = manager.run_backup()

        if result['success']:
            logger.info(f"Scheduled backup completed: {result['message']}")
        else:
            logger.error(f"Scheduled backup failed: {result['message']}")

    except Exception as e:
        logger.error(f"Scheduled backup error: {str(e)}")


def get_cron_trigger(settings):
    """
    Build cron trigger from settings.

    Args:
        settings: SiteSettings instance

    Returns:
        CronTrigger instance
    """
    frequency = settings.backup_frequency or 'daily'
    hour = settings.backup_hour or 3
    day_of_week = settings.backup_day or 0

    if frequency == 'hourly':
        # Every hour at minute 0
        return CronTrigger(minute=0)
    elif frequency == 'weekly':
        # Weekly on specified day at specified hour
        return CronTrigger(day_of_week=day_of_week, hour=hour, minute=0)
    else:  # daily (default)
        # Daily at specified hour
        return CronTrigger(hour=hour, minute=0)


def init_backup_scheduler(app):
    """
    Initialize the backup scheduler.

    Args:
        app: Flask application instance
    """
    global scheduler

    if scheduler is not None:
        logger.info("Scheduler already initialized")
        return

    # Create scheduler
    scheduler = BackgroundScheduler(daemon=True)

    # We need to wrap the job function to use app context
    def backup_job():
        with app.app_context():
            run_scheduled_backup()

    # Get settings and schedule job
    with app.app_context():
        from app.models.settings import SiteSettings

        try:
            settings = SiteSettings.get_settings()
            trigger = get_cron_trigger(settings)

            scheduler.add_job(
                backup_job,
                trigger=trigger,
                id='backup_job',
                name='Database Backup',
                replace_existing=True
            )

            scheduler.start()
            logger.info(f"Backup scheduler started (frequency: {settings.backup_frequency})")

        except Exception as e:
            logger.error(f"Failed to initialize backup scheduler: {str(e)}")


def update_backup_schedule():
    """
    Update the backup schedule after settings change.
    Call this when backup settings are modified.
    """
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler not initialized, cannot update schedule")
        return

    from app.models.settings import SiteSettings

    try:
        settings = SiteSettings.get_settings()

        # Remove existing job
        try:
            scheduler.remove_job('backup_job')
        except Exception:
            pass

        if not settings.ftp_enabled:
            logger.info("Backup disabled, job removed")
            return

        # Get the Flask app from the current context
        from flask import current_app
        app = current_app._get_current_object()

        def backup_job():
            with app.app_context():
                run_scheduled_backup()

        trigger = get_cron_trigger(settings)

        scheduler.add_job(
            backup_job,
            trigger=trigger,
            id='backup_job',
            name='Database Backup',
            replace_existing=True
        )

        logger.info(f"Backup schedule updated (frequency: {settings.backup_frequency}, hour: {settings.backup_hour})")

    except Exception as e:
        logger.error(f"Failed to update backup schedule: {str(e)}")


def get_next_backup_time():
    """Get the next scheduled backup time."""
    global scheduler

    if scheduler is None:
        return None

    try:
        job = scheduler.get_job('backup_job')
        if job and job.next_run_time:
            return job.next_run_time
    except Exception:
        pass

    return None


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Backup scheduler shut down")
