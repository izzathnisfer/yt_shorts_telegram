"""
YouTube search functionality using yt-dlp.
Search for videos and channels.
"""

import yt_dlp
from typing import List, Dict, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from .utils import format_duration, format_views
from config import SEARCH_RESULTS_LIMIT, COOKIES_PATH

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _search_sync(query: str, search_type: str = 'video', limit: int = 5) -> List[Dict[str, Any]]:
    """Synchronous search (runs in thread pool)."""
    try:
        if search_type == 'channel':
            search_url = f"ytsearchc{limit}:{query}"
        else:
            search_url = f"ytsearch{limit}:{query}"
        
        ydl_opts = {
            'quiet': False,  # Show errors for debugging
            'no_warnings': False,
            'extract_flat': True,
            'skip_download': True,
            # Use iOS/Android clients to bypass SSAP restrictions
            'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},
        }
        
        # Add cookies if file exists
        if COOKIES_PATH.exists():
            ydl_opts['cookiefile'] = str(COOKIES_PATH)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
            return info.get('entries', []) if info else []
    except Exception as e:
        logger.error(f"Search error for '{query}': {e}")
        return []


async def search_videos(query: str, limit: int = SEARCH_RESULTS_LIMIT) -> List[Dict[str, Any]]:
    """
    Search for YouTube videos.
    Returns list of video info dicts.
    """
    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(
        _executor,
        lambda: _search_sync(query, 'video', limit)
    )
    
    results = []
    for entry in entries:
        if not entry:
            continue
        
        video_id = entry.get('id', '')
        duration = entry.get('duration', 0) or 0
        
        results.append({
            'id': video_id,
            'title': entry.get('title', 'Unknown Title'),
            'duration': duration,
            'duration_string': format_duration(duration),
            'view_count': entry.get('view_count', 0),
            'view_count_string': format_views(entry.get('view_count', 0)),
            'url': entry.get('url', f'https://www.youtube.com/watch?v={video_id}'),
            'thumbnail': entry.get('thumbnail'),
            'channel_name': entry.get('channel', entry.get('uploader', 'Unknown')),
            'channel_id': entry.get('channel_id', ''),
            'channel_url': entry.get('channel_url', ''),
            'is_short': duration <= 60,
            'description': entry.get('description', '')[:200] if entry.get('description') else '',
        })
    
    return results


async def search_channels(query: str, limit: int = SEARCH_RESULTS_LIMIT) -> List[Dict[str, Any]]:
    """
    Search for YouTube channels.
    Returns list of channel info dicts.
    """
    # yt-dlp doesn't have great channel search, so we search videos and extract unique channels
    loop = asyncio.get_event_loop()
    
    # Search with more results to get diverse channels
    entries = await loop.run_in_executor(
        _executor,
        lambda: _search_sync(query, 'video', limit * 3)
    )
    
    # Extract unique channels
    seen_channels = set()
    channels = []
    
    for entry in entries:
        if not entry:
            continue
        
        channel_id = entry.get('channel_id', '')
        if not channel_id or channel_id in seen_channels:
            continue
        
        seen_channels.add(channel_id)
        
        channels.append({
            'id': channel_id,
            'name': entry.get('channel', entry.get('uploader', 'Unknown')),
            'url': entry.get('channel_url', entry.get('uploader_url', '')),
            'thumbnail': None,  # Would need separate request for channel thumbnail
        })
        
        if len(channels) >= limit:
            break
    
    return channels


async def search_lofi(duration_minutes: int = 60) -> List[Dict[str, Any]]:
    """
    Search for lofi music videos suitable for studying.
    Filters by duration to match requested focus time.
    """
    # Search queries optimized for lofi study music
    queries = [
        f"lofi hip hop study music {duration_minutes} minutes",
        f"lofi beats to study {duration_minutes}min",
        "lofi girl study beats mix",
        "chillhop study music",
    ]
    
    all_results = []
    
    for query in queries[:2]:  # Limit queries to save resources
        results = await search_videos(query, limit=5)
        all_results.extend(results)
    
    # Filter and sort by duration match
    min_duration = duration_minutes * 60 * 0.8  # Allow 20% shorter
    max_duration = duration_minutes * 60 * 1.5  # Allow 50% longer
    
    suitable = []
    for result in all_results:
        duration = result.get('duration', 0)
        if duration >= min_duration:
            # Score by how close duration matches (prefer longer than shorter)
            duration_diff = abs(duration - duration_minutes * 60)
            result['duration_score'] = duration_diff
            suitable.append(result)
    
    # Remove duplicates by video ID
    seen_ids = set()
    unique_results = []
    for result in suitable:
        if result['id'] not in seen_ids:
            seen_ids.add(result['id'])
            unique_results.append(result)
    
    # Sort by duration score (closest match first)
    unique_results.sort(key=lambda x: x.get('duration_score', float('inf')))
    
    return unique_results[:5]


async def get_trending_shorts(limit: int = 10) -> List[Dict[str, Any]]:
    """Get trending YouTube Shorts."""
    results = await search_videos("trending shorts", limit=limit * 2)
    
    # Filter to only actual shorts (<=60s)
    shorts = [r for r in results if r.get('is_short', False)]
    
    return shorts[:limit]
