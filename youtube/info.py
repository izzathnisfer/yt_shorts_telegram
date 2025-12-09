"""
YouTube video and channel information extraction using yt-dlp.
Memory-efficient extraction without downloading.
"""

import yt_dlp
from typing import Dict, Any, Optional, List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from .utils import extract_video_id, is_shorts_url, format_duration
from config import COOKIES_PATH

logger = logging.getLogger(__name__)

# Thread pool for running yt-dlp (which is synchronous)
_executor = ThreadPoolExecutor(max_workers=2)


def _get_yt_opts(quiet: bool = True) -> dict:
    """Get base yt-dlp options."""
    opts = {
        'quiet': quiet,
        'no_warnings': quiet,
        'extract_flat': False,
        'skip_download': True,
        'no_playlist': True,
        'ignoreerrors': True,
    }
    
    # Add cookies if file exists
    if COOKIES_PATH.exists():
        opts['cookiefile'] = str(COOKIES_PATH)
    
    return opts


def _extract_info_sync(url: str, opts: dict = None) -> Optional[Dict[str, Any]]:
    """Synchronous info extraction (runs in thread pool)."""
    try:
        ydl_opts = _get_yt_opts()
        if opts:
            ydl_opts.update(opts)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error extracting info from {url}: {e}")
        return None


async def get_video_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Extract video information without downloading.
    Returns normalized video info dict.
    """
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(_executor, _extract_info_sync, url)
    
    if not info:
        return None
    
    # Normalize the info
    video_id = info.get('id') or extract_video_id(url)
    duration = info.get('duration', 0) or 0
    
    # Determine if it's a short
    is_short = (
        is_shorts_url(url) or 
        duration <= 60 or
        info.get('height', 1920) > info.get('width', 1080)  # Vertical video
    )
    
    # Get best thumbnail
    thumbnails = info.get('thumbnails', [])
    thumbnail = None
    if thumbnails:
        # Prefer medium quality thumbnail
        for thumb in thumbnails:
            if thumb.get('id') == 'mqdefault' or 'mqdefault' in thumb.get('url', ''):
                thumbnail = thumb.get('url')
                break
        if not thumbnail:
            thumbnail = thumbnails[-1].get('url')  # Use highest quality available
    
    # Estimate file size for different qualities
    formats = info.get('formats', [])
    file_sizes = {}
    for fmt in formats:
        height = fmt.get('height')
        if height and fmt.get('filesize'):
            quality = str(height)
            if quality not in file_sizes or fmt['filesize'] > file_sizes[quality]:
                file_sizes[quality] = fmt['filesize']
    
    return {
        'id': video_id,
        'title': info.get('title', 'Unknown Title'),
        'description': info.get('description', ''),
        'duration': duration,
        'duration_string': format_duration(duration),
        'view_count': info.get('view_count', 0),
        'like_count': info.get('like_count', 0),
        'channel_id': info.get('channel_id', ''),
        'channel_name': info.get('channel', info.get('uploader', 'Unknown Channel')),
        'channel_url': info.get('channel_url', info.get('uploader_url', '')),
        'upload_date': info.get('upload_date', ''),
        'thumbnail': thumbnail,
        'is_short': is_short,
        'is_live': info.get('is_live', False),
        'webpage_url': info.get('webpage_url', url),
        'file_sizes': file_sizes,
        'width': info.get('width'),
        'height': info.get('height'),
    }


async def get_channel_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Extract channel information.
    """
    # For channel URLs, we need to get the channel page
    if '@' in url or '/channel/' in url or '/c/' in url or '/user/' in url:
        channel_url = url
    else:
        # Might be a video URL, extract channel from it
        video_info = await get_video_info(url)
        if video_info:
            channel_url = video_info.get('channel_url')
        else:
            return None
    
    if not channel_url:
        return None
    
    loop = asyncio.get_event_loop()
    
    # Get channel page info
    opts = {
        'extract_flat': True,
        'playlist_items': '1',  # Only get first item to extract channel info
    }
    
    # Try to get channel videos page
    videos_url = channel_url.rstrip('/') + '/videos'
    info = await loop.run_in_executor(
        _executor, 
        lambda: _extract_info_sync(videos_url, opts)
    )
    
    if not info:
        # Fallback to main channel URL
        info = await loop.run_in_executor(
            _executor,
            lambda: _extract_info_sync(channel_url, opts)
        )
    
    if not info:
        return None
    
    return {
        'id': info.get('channel_id', info.get('id', '')),
        'name': info.get('channel', info.get('uploader', info.get('title', 'Unknown'))),
        'url': info.get('channel_url', info.get('uploader_url', channel_url)),
        'description': info.get('description', ''),
        'subscriber_count': info.get('channel_follower_count', 0),
        'video_count': info.get('playlist_count', 0),
        'thumbnails': info.get('thumbnails', []),
    }


async def get_channel_videos(channel_url: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent videos from a channel.
    Returns list of video info dicts.
    """
    loop = asyncio.get_event_loop()
    
    # Ensure we're looking at the videos tab
    if '/videos' not in channel_url:
        videos_url = channel_url.rstrip('/') + '/videos'
    else:
        videos_url = channel_url
    
    opts = {
        'extract_flat': True,
        'playlist_items': f'1:{limit}',
    }
    
    info = await loop.run_in_executor(
        _executor,
        lambda: _extract_info_sync(videos_url, opts)
    )
    
    if not info:
        return []
    
    entries = info.get('entries', [])
    videos = []
    
    for entry in entries[:limit]:
        if not entry:
            continue
        
        video_id = entry.get('id', '')
        duration = entry.get('duration', 0) or 0
        
        videos.append({
            'id': video_id,
            'title': entry.get('title', 'Unknown Title'),
            'duration': duration,
            'duration_string': format_duration(duration),
            'view_count': entry.get('view_count', 0),
            'url': entry.get('url', f'https://www.youtube.com/watch?v={video_id}'),
            'thumbnail': entry.get('thumbnail'),
            'is_short': duration <= 60,
            'channel_name': info.get('channel', info.get('uploader', 'Unknown')),
            'channel_id': info.get('channel_id', ''),
        })
    
    return videos


async def is_short_video(url: str) -> bool:
    """Check if a video is a YouTube Short."""
    if is_shorts_url(url):
        return True
    
    info = await get_video_info(url)
    return info.get('is_short', False) if info else False


async def get_video_formats(url: str) -> List[Dict[str, Any]]:
    """Get available formats for a video."""
    loop = asyncio.get_event_loop()
    
    info = await loop.run_in_executor(_executor, _extract_info_sync, url)
    
    if not info:
        return []
    
    formats = []
    seen_heights = set()
    
    for fmt in info.get('formats', []):
        height = fmt.get('height')
        if not height or height in seen_heights:
            continue
        
        if fmt.get('vcodec') == 'none':  # Audio only
            continue
        
        seen_heights.add(height)
        
        formats.append({
            'format_id': fmt.get('format_id'),
            'height': height,
            'quality': f"{height}p",
            'ext': fmt.get('ext', 'mp4'),
            'filesize': fmt.get('filesize', 0),
            'vcodec': fmt.get('vcodec'),
            'acodec': fmt.get('acodec'),
        })
    
    # Sort by height descending
    formats.sort(key=lambda x: x['height'], reverse=True)
    
    return formats
