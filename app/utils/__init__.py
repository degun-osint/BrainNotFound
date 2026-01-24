# Utils package

from datetime import datetime
from zoneinfo import ZoneInfo

# Default timezone for display (France)
LOCAL_TZ = ZoneInfo('Europe/Paris')
UTC_TZ = ZoneInfo('UTC')


def to_local_time(dt):
    """Convert a UTC datetime to local time (Europe/Paris).

    Args:
        dt: A datetime object (assumed to be UTC if naive)

    Returns:
        A datetime object in local timezone
    """
    if dt is None:
        return None

    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)

    return dt.astimezone(LOCAL_TZ)


def format_datetime(dt, fmt='%d/%m/%Y à %H:%M'):
    """Format a UTC datetime to local time string.

    Args:
        dt: A datetime object (assumed to be UTC if naive)
        fmt: strftime format string

    Returns:
        Formatted string in local timezone
    """
    local_dt = to_local_time(dt)
    if local_dt is None:
        return '-'
    return local_dt.strftime(fmt)


def format_time(dt, fmt='%H:%M'):
    """Format a UTC datetime to local time string (time only).

    Args:
        dt: A datetime object (assumed to be UTC if naive)
        fmt: strftime format string

    Returns:
        Formatted time string in local timezone
    """
    return format_datetime(dt, fmt)
