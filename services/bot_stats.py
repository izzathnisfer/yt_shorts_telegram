"""
Centralized Bot Statistics Service.
Provides unified access to all bot stats for admin panel and future AI/MCP integration.
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from database import get_pool

logger = logging.getLogger(__name__)


async def get_user_summary(user_id: int) -> Dict[str, Any]:
    """Get comprehensive summary for a single user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # User info
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        
        if not user:
            return {"error": "User not found"}
        
        # Settings
        settings = await conn.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", user_id
        )
        
        # Subscription count
        sub_count = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE user_id = $1", user_id
        )
        
        # Watch history stats
        history_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_videos,
                COALESCE(SUM(duration), 0) as total_duration,
                COUNT(CASE WHEN is_short THEN 1 END) as shorts_count
            FROM video_history WHERE user_id = $1
        """, user_id)
        
        # Today's stats
        today_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as videos_today,
                COALESCE(SUM(duration), 0) as duration_today
            FROM video_history 
            WHERE user_id = $1 AND DATE(created_at) = CURRENT_DATE
        """, user_id)
        
        # Weekly stats
        week_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as videos_week,
                COALESCE(SUM(duration), 0) as duration_week
            FROM video_history 
            WHERE user_id = $1 AND created_at > NOW() - INTERVAL '7 days'
        """, user_id)
        
        # Queue count
        queue_count = await conn.fetchval(
            "SELECT COUNT(*) FROM queue WHERE user_id = $1", user_id
        )
        
        # Favorites count
        fav_count = await conn.fetchval(
            "SELECT COUNT(*) FROM favorites WHERE user_id = $1", user_id
        )
        
        # Time optimization score (0-100)
        # Based on: using queue, having limits, focus mode usage, etc.
        limit = settings['daily_limit'] if settings else 20
        score = 50  # Base score
        
        if limit > 0 and limit <= 20:
            score += 15  # Has a reasonable limit
        if queue_count > 0:
            score += 10  # Uses queue feature
        if sub_count > 0:
            score += 10  # Has subscriptions (intentional content)
        if fav_count > 0:
            score += 5  # Uses favorites
        
        # Reduce score if watching too much
        daily_avg = (week_stats['duration_week'] or 0) / 7 / 60  # minutes
        if daily_avg > 120:  # More than 2 hours average
            score -= 20
        elif daily_avg > 60:
            score -= 10
        
        score = max(0, min(100, score))
        
        # Estimated time saved (vs endless scrolling)
        total_videos = history_stats['total_videos'] or 0
        estimated_saved_minutes = (total_videos // 5) * 30
        
        return {
            "user_id": user_id,
            "username": user['username'],
            "first_name": user['first_name'],
            "created_at": user['created_at'].isoformat() if user['created_at'] else None,
            "subscriptions": sub_count,
            "queue_items": queue_count,
            "favorites": fav_count,
            "total_videos_watched": total_videos,
            "total_watch_time_seconds": history_stats['total_duration'] or 0,
            "shorts_watched": history_stats['shorts_count'] or 0,
            "today": {
                "videos": today_stats['videos_today'] or 0,
                "duration_seconds": today_stats['duration_today'] or 0,
            },
            "this_week": {
                "videos": week_stats['videos_week'] or 0,
                "duration_seconds": week_stats['duration_week'] or 0,
            },
            "time_optimization_score": score,
            "estimated_time_saved_minutes": estimated_saved_minutes,
            "settings": {
                "daily_limit": settings['daily_limit'] if settings else 20,
                "resolution": settings['resolution'] if settings else '720',
                "auto_download_shorts": settings['auto_download_shorts'] if settings else True,
            } if settings else {},
        }


async def get_bot_summary() -> Dict[str, Any]:
    """Get comprehensive bot-wide summary."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # User counts
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_users_24h = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM video_history WHERE created_at > NOW() - INTERVAL '1 day'"
        )
        active_users_7d = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM video_history WHERE created_at > NOW() - INTERVAL '7 days'"
        )
        
        # Content stats
        total_videos = await conn.fetchval("SELECT COUNT(*) FROM video_history")
        total_duration = await conn.fetchval("SELECT COALESCE(SUM(duration), 0) FROM video_history")
        
        # Subscriptions
        total_subs = await conn.fetchval("SELECT COUNT(*) FROM subscriptions")
        unique_channels = await conn.fetchval("SELECT COUNT(DISTINCT channel_id) FROM subscriptions")
        
        # Queue and favorites
        queue_items = await conn.fetchval("SELECT COUNT(*) FROM queue")
        favorites = await conn.fetchval("SELECT COUNT(*) FROM favorites")
        
        # Most watched channels
        top_channels = await conn.fetch("""
            SELECT channel_name, COUNT(*) as watch_count, COALESCE(SUM(duration), 0) as total_duration
            FROM video_history
            WHERE channel_name IS NOT NULL
            GROUP BY channel_name
            ORDER BY watch_count DESC
            LIMIT 5
        """)
        
        return {
            "users": {
                "total": total_users,
                "active_24h": active_users_24h or 0,
                "active_7d": active_users_7d or 0,
            },
            "content": {
                "total_videos_watched": total_videos or 0,
                "total_watch_time_seconds": total_duration or 0,
                "total_watch_time_hours": (total_duration or 0) // 3600,
            },
            "subscriptions": {
                "total": total_subs or 0,
                "unique_channels": unique_channels or 0,
            },
            "engagement": {
                "queue_items": queue_items or 0,
                "favorites": favorites or 0,
            },
            "top_channels": [
                {
                    "name": ch['channel_name'],
                    "watch_count": ch['watch_count'],
                    "duration_seconds": ch['total_duration']
                }
                for ch in top_channels
            ],
        }


async def get_channel_analytics(channel_id: str = None) -> Dict[str, Any]:
    """Get analytics for channels."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if channel_id:
            # Specific channel
            stats = await conn.fetchrow("""
                SELECT 
                    channel_name,
                    COUNT(*) as videos_watched,
                    COUNT(DISTINCT user_id) as unique_viewers,
                    COALESCE(SUM(duration), 0) as total_duration
                FROM video_history
                WHERE channel_id = $1
                GROUP BY channel_name
            """, channel_id)
            
            if not stats:
                return {"error": "Channel not found in history"}
            
            return {
                "channel_id": channel_id,
                "channel_name": stats['channel_name'],
                "videos_watched": stats['videos_watched'],
                "unique_viewers": stats['unique_viewers'],
                "total_duration_seconds": stats['total_duration'],
            }
        else:
            # All channels summary
            channels = await conn.fetch("""
                SELECT 
                    channel_id, channel_name,
                    COUNT(*) as videos_watched,
                    COUNT(DISTINCT user_id) as unique_viewers
                FROM video_history
                WHERE channel_id IS NOT NULL
                GROUP BY channel_id, channel_name
                ORDER BY videos_watched DESC
                LIMIT 20
            """)
            
            return {
                "channels": [
                    {
                        "id": ch['channel_id'],
                        "name": ch['channel_name'],
                        "videos_watched": ch['videos_watched'],
                        "unique_viewers": ch['unique_viewers'],
                    }
                    for ch in channels
                ]
            }
