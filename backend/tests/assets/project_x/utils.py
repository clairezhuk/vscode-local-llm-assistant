import datetime

def get_version():
    """Returns the current utility version."""
    return "1.0.4-patch"

def format_date(date_raw):
    """
    Takes a raw date string (YYYY-MM-DD) and returns a 
    standardized formatted string for the reporting system.
    """
    if not date_raw:
        return "Formatted: N/A"
    return f"Formatted date: {date_raw}"

def validate_timestamp(ts):
    """Checks if the timestamp is in the past."""
    try:
        dt = datetime.datetime.strptime(ts, '%Y-%m-%d')
        return dt < datetime.datetime.now()
    except ValueError:
        return False

def log_event(message, level="INFO"):
    """Logs an event to the internal system."""
    print(f"[{level}] {message}")