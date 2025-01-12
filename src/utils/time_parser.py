"""Time parsing utilities."""
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

def parse_date(date_str: str) -> datetime:
    """Parse a date string in format DDMM, DD/MM or DD.MM."""
    # Remove any separators and get just the numbers
    date_numbers = re.sub(r'[/.-]', '', date_str)
    
    if len(date_numbers) != 4:
        raise ValueError("Invalid date format. Please use DDMM, DD/MM or DD.MM")
        
    try:
        day = int(date_numbers[:2])
        month = int(date_numbers[2:])
        
        # Get current year
        current_year = datetime.now(ZoneInfo("Europe/Berlin")).year
        
        # Create date object
        return datetime(current_year, month, day)
        
    except ValueError as e:
        raise ValueError("Invalid date. Please check day and month values.") from e

def parse_time(time_str: str) -> tuple[int, int]:
    """Parse a time string in format HHMM or HH:MM."""
    # Remove any separators and get just the numbers
    time_numbers = time_str.replace(':', '')
    
    if len(time_numbers) != 4:
        raise ValueError("Invalid time format. Please use HHMM or HH:MM")
        
    try:
        hours = int(time_numbers[:2])
        minutes = int(time_numbers[2:])
        
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise ValueError
            
        return hours, minutes
        
    except ValueError as e:
        raise ValueError("Invalid time. Please check hours and minutes values.") from e

def parse_datetime(date_str: str, time_str: str) -> datetime:
    """Parse date and time strings into a datetime object."""
    try:
        # Parse date and time separately
        date_obj = parse_date(date_str)
        hours, minutes = parse_time(time_str)
        
        # Create datetime in German timezone
        german_tz = ZoneInfo("Europe/Berlin")
        dt = datetime(
            date_obj.year,
            date_obj.month,
            date_obj.day,
            hours,
            minutes,
            tzinfo=german_tz
        )
        
        # Convert to UTC for storage
        return dt.astimezone(ZoneInfo("UTC"))
        
    except ValueError as e:
        raise ValueError(f"Error parsing date/time: {str(e)}")

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