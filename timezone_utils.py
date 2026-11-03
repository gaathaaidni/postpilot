"""
PostPilot Timezone & Datetime Utilities
Provides robust, timezone-safe datetime parsing, IANA timezone validation,
and bidirectional conversion between local times and UTC.
Zero third-party dependencies (built upon Python 3.9+ standard library zoneinfo).
"""
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COMMON_TIMEZONES = [
    "UTC",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "Australia/Sydney",
    "Pacific/Auckland"
]

def validate_timezone_name(tz_name):
    """
    Validates whether tz_name is a valid IANA timezone identifier.
    Returns the canonical timezone string if valid.
    Raises ValueError with explanatory message if invalid.
    """
    if not tz_name or not isinstance(tz_name, str):
        raise ValueError("Timezone must be a non-empty string identifier (e.g. 'UTC', 'Asia/Kolkata').")
    
    clean_tz = tz_name.strip()
    try:
        ZoneInfo(clean_tz)
        return clean_tz
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        raise ValueError(
            f"Invalid or unrecognized IANA timezone identifier: '{tz_name}'. "
            f"Must be a standard IANA timezone name (e.g. 'UTC', 'America/New_York', 'Asia/Kolkata')."
        )

def parse_and_convert_to_utc(timestamp_str, tz_name=None, org_default_tz='UTC', allow_past=False):
    """
    Strictly validates and converts an ISO 8601 date/time input to standardized UTC.
    
    Arguments:
        timestamp_str (str): ISO 8601 string (e.g. '2026-11-04T15:30:00' or '2026-11-04T15:30:00+05:30').
        tz_name (str, optional): Target timezone for naive timestamps.
        org_default_tz (str, optional): Fallback organization timezone if tz_name is omitted.
        allow_past (bool): If False, rejects timestamps scheduled in the past.

    Returns:
        tuple: (utc_datetime, resolved_timezone_str, utc_formatted_str)

    Raises:
        ValueError: For malformed timestamps, invalid timezones, or past times.
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        raise ValueError("Scheduled date/time is required and must be an ISO 8601 string.")

    raw_ts = timestamp_str.strip()
    # Normalize trailing Z to +00:00 for fromisoformat compatibility
    clean_ts = raw_ts.replace('Z', '+00:00')

    try:
        dt = datetime.fromisoformat(clean_ts)
    except Exception as e:
        raise ValueError(
            f"Malformed date/time string: '{timestamp_str}'. "
            f"Expected valid ISO 8601 format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DDTHH:MM:SS±HH:MM"
        )

    if dt.tzinfo is not None:
        # Timestamp contains explicit UTC offset
        utc_dt = dt.astimezone(timezone.utc)
        resolved_tz = validate_timezone_name(tz_name) if tz_name else "UTC"
    else:
        # Naive timestamp: requires timezone context
        target_tz_str = tz_name if tz_name else org_default_tz
        if not target_tz_str:
            target_tz_str = "UTC"
        resolved_tz = validate_timezone_name(target_tz_str)
        local_tz = ZoneInfo(resolved_tz)
        # Attach timezone without shifting wall-clock digits
        dt_localized = dt.replace(tzinfo=local_tz)
        utc_dt = dt_localized.astimezone(timezone.utc)

    # Validate against past scheduling times
    now_utc = datetime.now(timezone.utc)
    # Allow 60-second grace period for transit latency
    if not allow_past and utc_dt < (now_utc - timedelta(seconds=60)):
        raise ValueError(
            f"Cannot schedule post in the past: requested time '{timestamp_str}' resolves to "
            f"{utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}, which is earlier than current time "
            f"{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}."
        )

    utc_str = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
    return utc_dt, resolved_tz, utc_str

def convert_utc_to_local(utc_val, tz_name='UTC'):
    """
    Converts a stored UTC timestamp (string or datetime) to localized representation.
    Returns:
        dict with 'utc', 'local_iso', 'local_display', 'timezone', and 'offset'
    """
    target_tz = validate_timezone_name(tz_name or 'UTC')
    zi = ZoneInfo(target_tz)

    if isinstance(utc_val, datetime):
        if utc_val.tzinfo is None:
            utc_dt = utc_val.replace(tzinfo=timezone.utc)
        else:
            utc_dt = utc_val.astimezone(timezone.utc)
    else:
        # String parsing
        s = str(utc_val).replace('T', ' ')[:19]
        dt_naive = datetime.fromisoformat(s)
        utc_dt = dt_naive.replace(tzinfo=timezone.utc)

    local_dt = utc_dt.astimezone(zi)
    return {
        "utc": utc_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "local_iso": local_dt.isoformat(),
        "local_display": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": target_tz,
        "offset": local_dt.strftime("%z")
    }
