"""
YouTube utility functions.
URL parsing, formatting, and helper functions.
"""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs


# Regex patterns for YouTube URLs
YOUTUBE_VIDEO_PATTERNS = [
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
]

YOUTUBE_CHANNEL_PATTERNS = [
    r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
    r'youtube\.com/c/([a-zA-Z0-9_-]+)',
    r'youtube\.com/@([a-zA-Z0-9_-]+)',
    r'youtube\.com/user/([a-zA-Z0-9_-]+)',
]

YOUTUBE_PLAYLIST_PATTERN = r'youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)'


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    if not url:
        return None
    
    for pattern in YOUTUBE_VIDEO_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def extract_channel_id(url: str) -> Optional[Tuple[str, str]]:
    """
    Extract channel identifier from URL.
    Returns tuple of (type, id) where type is 'channel', 'c', 'user', or 'handle'.
    """
    if not url:
        return None
    
    # Check for @handle format
    match = re.search(r'youtube\.com/@([a-zA-Z0-9_-]+)', url)
    if match:
        return ('handle', match.group(1))
    
    # Check for /channel/ format
    match = re.search(r'youtube\.com/channel/([a-zA-Z0-9_-]+)', url)
    if match:
        return ('channel', match.group(1))
    
    # Check for /c/ format
    match = re.search(r'youtube\.com/c/([a-zA-Z0-9_-]+)', url)
    if match:
        return ('c', match.group(1))
    
    # Check for /user/ format
    match = re.search(r'youtube\.com/user/([a-zA-Z0-9_-]+)', url)
    if match:
        return ('user', match.group(1))
    
    return None


def extract_playlist_id(url: str) -> Optional[str]:
    """Extract playlist ID from URL."""
    if not url:
        return None
    
    match = re.search(YOUTUBE_PLAYLIST_PATTERN, url)
    return match.group(1) if match else None


def is_youtube_url(url: str) -> bool:
    """Check if URL is a valid YouTube URL."""
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        return parsed.netloc in [
            'youtube.com', 'www.youtube.com', 
            'youtu.be', 'm.youtube.com',
            'music.youtube.com'
        ]
    except:
        return False


def is_shorts_url(url: str) -> bool:
    """Check if URL is a YouTube Shorts URL."""
    return 'youtube.com/shorts/' in url if url else False


def build_video_url(video_id: str) -> str:
    """Build standard YouTube video URL from ID."""
    return f"https://www.youtube.com/watch?v={video_id}"


def build_channel_url(channel_id: str, id_type: str = 'channel') -> str:
    """Build YouTube channel URL."""
    if id_type == 'handle':
        return f"https://www.youtube.com/@{channel_id}"
    elif id_type == 'channel':
        return f"https://www.youtube.com/channel/{channel_id}"
    elif id_type == 'c':
        return f"https://www.youtube.com/c/{channel_id}"
    else:
        return f"https://www.youtube.com/user/{channel_id}"


def format_duration(seconds) -> str:
    """Format duration in seconds to human readable string."""
    if seconds is None or seconds < 0:
        return "0:00"
    
    seconds = int(seconds)  # Ensure integer
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_duration_long(seconds) -> str:
    """Format duration to long readable string (e.g., '2h 30m')."""
    if seconds is None or seconds < 0:
        return "0m"
    
    seconds = int(seconds)  # Ensure integer
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}m")
    
    return " ".join(parts)


def format_views(count: int) -> str:
    """Format view count to human readable string (e.g., '1.2M')."""
    if count is None:
        return "0"
    
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    elif count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)


def format_file_size(bytes_size: int) -> str:
    """Format file size to human readable string."""
    if bytes_size is None or bytes_size < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    
    return f"{bytes_size:.1f} TB"


def parse_duration_string(duration_str: str) -> Optional[int]:
    """
    Parse duration string to seconds.
    Supports formats: '1:30', '1:30:00', '90', '1h30m', '1h', '30m', '2h 30m'
    """
    if not duration_str:
        return None
    
    duration_str = duration_str.strip().lower()
    
    # Try HH:MM:SS or MM:SS format
    if ':' in duration_str:
        parts = duration_str.split(':')
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
    
    # Try human format (1h30m, 2h, 30m, etc.)
    total_seconds = 0
    
    # Extract hours
    hour_match = re.search(r'(\d+)\s*h', duration_str)
    if hour_match:
        total_seconds += int(hour_match.group(1)) * 3600
    
    # Extract minutes
    min_match = re.search(r'(\d+)\s*m', duration_str)
    if min_match:
        total_seconds += int(min_match.group(1)) * 60
    
    # Extract seconds
    sec_match = re.search(r'(\d+)\s*s', duration_str)
    if sec_match:
        total_seconds += int(sec_match.group(1))
    
    if total_seconds > 0:
        return total_seconds
    
    # Try plain number (assume seconds)
    try:
        return int(duration_str)
    except ValueError:
        pass
    
    return None


def parse_time_range(time_range: str) -> Optional[Tuple[int, int]]:
    """
    Parse time range string to start and end seconds.
    Format: 'start-end' where start/end can be 'MM:SS' or 'HH:MM:SS'
    Example: '1:30-5:00' returns (90, 300)
    """
    if not time_range or '-' not in time_range:
        return None
    
    parts = time_range.split('-')
    if len(parts) != 2:
        return None
    
    start = parse_duration_string(parts[0].strip())
    end = parse_duration_string(parts[1].strip())
    
    if start is None or end is None:
        return None
    
    if start >= end:
        return None
    
    return (start, end)


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Sanitize filename for filesystem."""
    if not filename:
        return "video"
    
    # Remove/replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = ''.join(c for c in filename if ord(c) >= 32)
    
    # Truncate if too long
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    return filename.strip() or "video"


def estimate_file_size(duration: int, resolution: str) -> int:
    """
    Estimate file size in MB based on duration and resolution.
    This is a rough estimate for planning purposes.
    """
    # Approximate bitrates in kbps
    bitrates = {
        '360': 1000,
        '480': 2500,
        '720': 5000,
        '1080': 8000,
    }
    
    bitrate = bitrates.get(resolution, 5000)
    
    # Size in bytes = bitrate (kbps) * duration (s) / 8 * 1000
    size_bytes = (bitrate * duration * 1000) / 8
    size_mb = size_bytes / (1024 * 1024)
    
    return int(size_mb)
