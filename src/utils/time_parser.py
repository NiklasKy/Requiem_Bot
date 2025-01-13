"""Time parsing utilities."""
from datetime import datetime, timedelta
from typing import Tuple

def parse_time(time_str: str) -> Tuple[int, int]:
    """Parse a time string into hour and minute.
    
    Args:
        time_str: Time string in format HHMM or HH:MM
        
    Returns:
        Tuple of (hour, minute)
        
    Raises:
        ValueError: If time format is invalid
    """
    # Remove any separators
    time_str = time_str.replace(":", "")
    
    if not time_str.isdigit() or len(time_str) != 4:
        raise ValueError("Invalid time format. Please use HHMM or HH:MM")
        
    hour = int(time_str[:2])
    minute = int(time_str[2:])
    
    # Basic validation
    if hour < 0 or hour > 23:
        raise ValueError("Hour must be between 0 and 23")
    if minute < 0 or minute > 59:
        raise ValueError("Minute must be between 0 and 59")
        
    return hour, minute

def parse_date(date_str: str) -> datetime:
    """Parse a date string into a date object.
    
    Args:
        date_str: Date string in format DDMM, DD/MM or DD.MM
        
    Returns:
        datetime object with just the date part set (time will be 00:00)
        
    Raises:
        ValueError: If date format is invalid
    """
    # Remove any separators
    date_str = date_str.replace(".", "").replace("/", "")
    
    if not date_str.isdigit() or len(date_str) != 4:
        raise ValueError("Invalid date format. Please use DDMM, DD/MM or DD.MM")
        
    day = int(date_str[:2])
    month = int(date_str[2:])
    
    # Basic validation
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")
    if day < 1 or day > 31:
        raise ValueError("Day must be between 1 and 31")
        
    # Create date with current year
    return datetime(year=datetime.utcnow().year, month=month, day=day)

def parse_datetime(date_str: str, time_str: str) -> datetime:
    """Parse date and time strings into a datetime object.
    
    Args:
        date_str: Date string in format DDMM, DD/MM or DD.MM
        time_str: Time string in format HHMM or HH:MM
        
    Returns:
        datetime object
        
    Raises:
        ValueError: If date or time format is invalid
    """
    # Parse date
    date = parse_date(date_str)
    
    # Parse time
    hour, minute = parse_time(time_str)
    
    # Create datetime object with current year
    dt = datetime(
        year=date.year,
        month=date.month,
        day=date.day,
        hour=hour,
        minute=minute
    )
    
    # Check if the datetime is in the past
    current_time = datetime.utcnow()
    if dt < current_time:
        # If it's within 14 days in the past, it's probably a mistake
        days_in_past = (current_time - dt).days
        if days_in_past <= 14:
            raise ValueError("The start date/time cannot be in the past! Please check your input.")
        
        # If it's more than 14 days in the past, move it to next year
        dt = dt.replace(year=dt.year + 1)
    
    return dt

def format_duration(duration: timedelta) -> str:
    """Format a timedelta into a human-readable string.
    
    Args:
        duration: timedelta object
        
    Returns:
        Formatted duration string
    """
    days = duration.days
    hours = duration.seconds // 3600
    minutes = (duration.seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours > 0:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    
    if not parts:
        return "less than a minute"
    
    if len(parts) == 1:
        return parts[0]
    
    return f"{', '.join(parts[:-1])} and {parts[-1]}" 