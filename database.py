"""
Database operations for YouTube Shorts Bot.
Uses async PostgreSQL (asyncpg) for non-blocking operations.
Handles all user data, subscriptions, queue, and statistics.
"""

import asyncpg
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import logging

from config import (
    DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, 
    DATABASE_NAME, DATABASE_PORT,
    DEFAULT_CHECK_INTERVAL, DEFAULT_RESOLUTION, DEFAULT_DAILY_LIMIT,
    DEFAULT_QUIET_START, DEFAULT_QUIET_END, DEFAULT_TIMEZONE
)

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        # Extract endpoint ID from hostname (for Neon/Koyeb PostgreSQL)
        # e.g., "ep-tiny-union-ahh5fbhi.c-3.us-east-1.pg.koyeb.app" -> "ep-tiny-union-ahh5fbhi"
        endpoint_id = DATABASE_HOST.split('.')[0]
        
        _pool = await asyncpg.create_pool(
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            database=DATABASE_NAME,
            min_size=1,  # Reduced from 2 to minimize idle connections
            max_size=10,
            ssl='require',  # Koyeb requires SSL
            server_settings={'options': f'endpoint={endpoint_id}'}  # Required for Neon/Koyeb
        )
        logger.info("Database connection pool created")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def init_db():
    """Initialize database with all required tables."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # User settings
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                daily_limit INTEGER DEFAULT {DEFAULT_DAILY_LIMIT},
                check_interval INTEGER DEFAULT {DEFAULT_CHECK_INTERVAL},
                resolution TEXT DEFAULT '{DEFAULT_RESOLUTION}',
                quiet_start TEXT DEFAULT '{DEFAULT_QUIET_START}',
                quiet_end TEXT DEFAULT '{DEFAULT_QUIET_END}',
                auto_download_shorts BOOLEAN DEFAULT TRUE,
                focus_until TIMESTAMP,
                timezone TEXT DEFAULT '{DEFAULT_TIMEZONE}',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Channel subscriptions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                channel_id TEXT,
                channel_name TEXT,
                channel_url TEXT,
                nickname TEXT,
                is_priority BOOLEAN DEFAULT FALSE,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, channel_id)
            )
        """)
        
        # Watch queue
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                video_id TEXT,
                video_url TEXT,
                title TEXT,
                channel_name TEXT,
                duration INTEGER,
                thumbnail_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_downloaded BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        # Video history (for duplicate detection & stats)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS video_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                video_id TEXT,
                title TEXT,
                channel_id TEXT,
                channel_name TEXT,
                duration INTEGER,
                is_short BOOLEAN,
                is_lofi BOOLEAN DEFAULT FALSE,
                watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        # Daily stats
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                date DATE,
                videos_watched INTEGER DEFAULT 0,
                shorts_watched INTEGER DEFAULT 0,
                lofi_sessions INTEGER DEFAULT 0,
                total_duration INTEGER DEFAULT 0,
                lofi_duration INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, date)
            )
        """)
        
        # Channel stats (for per-channel time tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                channel_id TEXT,
                channel_name TEXT,
                videos_watched INTEGER DEFAULT 0,
                total_duration INTEGER DEFAULT 0,
                last_watched TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, channel_id)
            )
        """)
        
        # Favorites
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                video_id TEXT,
                video_url TEXT,
                title TEXT,
                channel_name TEXT,
                duration INTEGER,
                thumbnail_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        # Channel videos - tracks all videos from subscribed channels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_videos (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                duration INTEGER,
                is_short BOOLEAN DEFAULT FALSE,
                upload_date TIMESTAMP,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel_id, video_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_videos_channel 
            ON channel_videos(channel_id)
        """)
        
        # Notification log - tracks sent notifications
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                video_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                notification_type TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, video_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_log_user 
            ON notification_log(user_id)
        """)
        
        # Snoozed notifications - tracks snooze reminders
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS snoozed_notifications (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                video_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                video_title TEXT,
                snoozed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                remind_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                UNIQUE(user_id, video_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snoozed_remind 
            ON snoozed_notifications(remind_at, status)
        """)
        
        # Admin settings - configurable settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default admin settings
        await conn.execute("""
            INSERT INTO admin_settings (key, value) 
            VALUES ('check_interval_minutes', '15')
            ON CONFLICT (key) DO NOTHING
        """)
        
        logger.info("Database tables initialized")


# ============ User Operations ============

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
    """Get existing user or create new one with default settings."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        
        if row:
            return dict(row)
        
        # Create new user
        await conn.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES ($1, $2, $3)",
            user_id, username, first_name
        )
        
        # Create default settings
        await conn.execute(
            "INSERT INTO user_settings (user_id) VALUES ($1)",
            user_id
        )
        
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "is_active": True
        }


async def get_all_active_users() -> List[Dict[str, Any]]:
    """Get all active users for scheduled tasks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE is_active = TRUE"
        )
        return [dict(row) for row in rows]


# ============ Settings Operations ============

async def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Get user settings."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", user_id
        )
        
        if row:
            return dict(row)
        
        # Create default settings if not exists
        await conn.execute(
            "INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
            user_id
        )
        
        return {
            "user_id": user_id,
            "daily_limit": DEFAULT_DAILY_LIMIT,
            "check_interval": DEFAULT_CHECK_INTERVAL,
            "resolution": DEFAULT_RESOLUTION,
            "quiet_start": DEFAULT_QUIET_START,
            "quiet_end": DEFAULT_QUIET_END,
            "auto_download_shorts": True,
            "focus_until": None,
            "timezone": DEFAULT_TIMEZONE
        }


async def update_user_settings(user_id: int, **kwargs) -> None:
    """Update user settings with provided values."""
    if not kwargs:
        return
    
    # Build SET clause with positional parameters
    set_parts = []
    values = []
    for i, (k, v) in enumerate(kwargs.items(), start=1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    
    set_clause = ", ".join(set_parts)
    values.append(user_id)
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE user_settings SET {set_clause} WHERE user_id = ${len(values)}",
            *values
        )


async def set_focus_mode(user_id: int, until: Optional[datetime]) -> None:
    """Set or clear focus mode for user."""
    await update_user_settings(user_id, focus_until=until)


async def is_in_focus_mode(user_id: int) -> tuple[bool, Optional[datetime]]:
    """Check if user is in focus mode and return end time."""
    settings = await get_user_settings(user_id)
    focus_until = settings.get("focus_until")
    
    if not focus_until:
        return False, None
    
    # Handle if it's already a datetime object
    if isinstance(focus_until, datetime):
        end_time = focus_until
    else:
        end_time = datetime.fromisoformat(str(focus_until))
    
    if end_time <= datetime.now():
        # Focus mode expired, clear it
        await set_focus_mode(user_id, None)
        return False, None
    
    return True, end_time


# ============ Subscription Operations ============

async def add_subscription(user_id: int, channel_id: str, channel_name: str, 
                          channel_url: str, is_priority: bool = False) -> bool:
    """Add a channel subscription. Returns True if added, False if already exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO subscriptions 
                   (user_id, channel_id, channel_name, channel_url, is_priority)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, channel_id, channel_name, channel_url, is_priority
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def remove_subscription(user_id: int, channel_id: str) -> bool:
    """Remove a channel subscription."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM subscriptions WHERE user_id = $1 AND channel_id = $2",
            user_id, channel_id
        )
        # asyncpg returns 'DELETE X' where X is the row count
        return result.split()[-1] != '0'


async def get_subscriptions(user_id: int) -> List[Dict[str, Any]]:
    """Get all subscriptions for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM subscriptions 
               WHERE user_id = $1 
               ORDER BY is_priority DESC, channel_name ASC""",
            user_id
        )
        return [dict(row) for row in rows]


async def get_subscription(user_id: int, channel_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific subscription."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM subscriptions WHERE user_id = $1 AND channel_id = $2",
            user_id, channel_id
        )
        return dict(row) if row else None


async def set_channel_priority(user_id: int, channel_id: str, is_priority: bool) -> None:
    """Toggle priority status for a channel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET is_priority = $1 WHERE user_id = $2 AND channel_id = $3",
            is_priority, user_id, channel_id
        )


async def set_channel_nickname(user_id: int, channel_id: str, nickname: Optional[str]) -> None:
    """Set a custom nickname for a channel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET nickname = $1 WHERE user_id = $2 AND channel_id = $3",
            nickname, user_id, channel_id
        )


# ============ Queue Operations ============

async def add_to_queue(user_id: int, video_id: str, video_url: str, title: str,
                       channel_name: str, duration: int, thumbnail_url: str = None) -> bool:
    """Add video to watch queue. Returns True if added, False if already exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO queue 
                   (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                user_id, video_id, video_url, title, channel_name, duration, thumbnail_url
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def remove_from_queue(user_id: int, video_id: str) -> bool:
    """Remove video from queue."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM queue WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )
        return result.split()[-1] != '0'


async def get_queue(user_id: int) -> List[Dict[str, Any]]:
    """Get all queued videos for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM queue WHERE user_id = $1 ORDER BY added_at ASC",
            user_id
        )
        return [dict(row) for row in rows]


async def clear_queue(user_id: int) -> int:
    """Clear all queued videos. Returns count of removed items."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM queue WHERE user_id = $1",
            user_id
        )
        return int(result.split()[-1])


async def mark_queue_downloaded(user_id: int, video_id: str) -> None:
    """Mark a queued video as downloaded."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE queue SET is_downloaded = TRUE WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )


# ============ Video History & Duplicate Detection ============

async def add_to_history(user_id: int, video_id: str, title: str, channel_id: str,
                         channel_name: str, duration: int, is_short: bool,
                         is_lofi: bool = False, source: str = "direct") -> bool:
    """Add video to history. Returns True if new, False if duplicate."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO video_history 
                   (user_id, video_id, title, channel_id, channel_name, duration, is_short, is_lofi, source)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                user_id, video_id, title, channel_id, channel_name, duration, is_short, is_lofi, source
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def check_duplicate(user_id: int, video_id: str) -> Optional[Dict[str, Any]]:
    """Check if video was already downloaded. Returns history entry if exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM video_history WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )
        return dict(row) if row else None


async def mark_video_seen(user_id: int, video_id: str) -> None:
    """Mark a video as seen (for subscription new video detection)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO seen_videos (user_id, video_id) VALUES ($1, $2) ON CONFLICT (user_id, video_id) DO NOTHING",
            user_id, video_id
        )


async def is_video_seen(user_id: int, video_id: str) -> bool:
    """Check if a video has been seen by user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM seen_videos WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )
        return row is not None


async def get_recent_lofi_ids(user_id: int, days: int = 30) -> set:
    """Get video IDs of lofi tracks sent to user within the last N days."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT video_id FROM video_history 
               WHERE user_id = $1 AND is_lofi = TRUE 
               AND watched_at > NOW() - INTERVAL '%s days'""" % days,
            user_id
        )
        return {row['video_id'] for row in rows}


# ============ Channel Videos & Notification Operations ============

async def add_channel_video(channel_id: str, video_id: str, title: str, 
                            duration: int, is_short: bool, upload_date=None) -> bool:
    """
    Add a video to channel_videos table.
    Returns True if newly added, False if already exists.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO channel_videos 
                   (channel_id, video_id, title, duration, is_short, upload_date)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                channel_id, video_id, title, duration, is_short, upload_date
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def get_channel_video(video_id: str) -> Optional[Dict[str, Any]]:
    """Get a video record from channel_videos."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM channel_videos WHERE video_id = $1",
            video_id
        )
        return dict(row) if row else None


async def has_notification_sent(user_id: int, video_id: str) -> bool:
    """Check if notification was already sent to user for this video."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM notification_log WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )
        return row is not None


async def log_notification(user_id: int, video_id: str, channel_id: str, 
                           notification_type: str = 'video') -> None:
    """Log that a notification was sent to user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO notification_log 
               (user_id, video_id, channel_id, notification_type)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id, video_id) DO NOTHING""",
            user_id, video_id, channel_id, notification_type
        )


async def add_snooze(user_id: int, video_id: str, channel_id: str, 
                     video_title: str, remind_at) -> None:
    """Add a snoozed notification."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO snoozed_notifications 
               (user_id, video_id, channel_id, video_title, remind_at)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (user_id, video_id) 
               DO UPDATE SET remind_at = $5, status = 'pending'""",
            user_id, video_id, channel_id, video_title, remind_at
        )


async def get_due_snoozes() -> List[Dict[str, Any]]:
    """Get all snoozed notifications that are due for reminder."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM snoozed_notifications 
               WHERE remind_at <= NOW() AND status = 'pending'"""
        )
        return [dict(row) for row in rows]


async def mark_snooze_reminded(snooze_id: int) -> None:
    """Mark a snoozed notification as reminded."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE snoozed_notifications SET status = 'reminded' WHERE id = $1",
            snooze_id
        )


async def dismiss_snooze(user_id: int, video_id: str) -> None:
    """Dismiss a snoozed notification."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE snoozed_notifications 
               SET status = 'dismissed' 
               WHERE user_id = $1 AND video_id = $2""",
            user_id, video_id
        )


async def get_admin_setting(key: str, default: str = None) -> Optional[str]:
    """Get an admin setting value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM admin_settings WHERE key = $1",
            key
        )
        return row['value'] if row else default


async def set_admin_setting(key: str, value: str) -> None:
    """Set an admin setting value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO admin_settings (key, value, updated_at)
               VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()""",
            key, value
        )


async def get_all_subscribed_channels() -> List[Dict[str, Any]]:
    """Get all unique channels that have at least one subscriber."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT channel_id, channel_name, channel_url 
               FROM subscriptions"""
        )
        return [dict(row) for row in rows]


async def get_channel_subscribers(channel_id: str) -> List[Dict[str, Any]]:
    """Get all users subscribed to a channel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT user_id, subscribed_at, is_priority, nickname 
               FROM subscriptions WHERE channel_id = $1""",
            channel_id
        )
        return [dict(row) for row in rows]


# ============ OPTIMIZED BATCH FUNCTIONS ============
# These reduce DB compute by combining multiple queries into single operations

async def get_channels_with_subscribers() -> List[Dict[str, Any]]:
    """
    Get all channels with their subscribers in a single query.
    Returns: [{channel_id, channel_name, channel_url, subscribers: [{user_id, subscribed_at, ...}]}]
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT channel_id, channel_name, channel_url, 
                      user_id, subscribed_at, is_priority, nickname
               FROM subscriptions 
               ORDER BY channel_id"""
        )
        
        # Group by channel
        channels = {}
        for row in rows:
            cid = row['channel_id']
            if cid not in channels:
                channels[cid] = {
                    'channel_id': cid,
                    'channel_name': row['channel_name'],
                    'channel_url': row['channel_url'],
                    'subscribers': []
                }
            channels[cid]['subscribers'].append({
                'user_id': row['user_id'],
                'subscribed_at': row['subscribed_at'],
                'is_priority': row['is_priority'],
                'nickname': row['nickname']
            })
        
        return list(channels.values())


async def get_sent_notifications_bulk(user_id: int, video_ids: List[str]) -> set:
    """
    Check which videos have already been notified in bulk.
    Returns: set of video_ids that were already sent.
    """
    if not video_ids:
        return set()
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT video_id FROM notification_log 
               WHERE user_id = $1 AND video_id = ANY($2)""",
            user_id, video_ids
        )
        return {row['video_id'] for row in rows}


async def log_notifications_bulk(notifications: List[tuple]) -> None:
    """
    Log multiple notifications in a single batch insert.
    notifications: [(user_id, video_id, channel_id, notification_type), ...]
    """
    if not notifications:
        return
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO notification_log (user_id, video_id, channel_id, notification_type)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id, video_id) DO NOTHING""",
            notifications
        )


async def add_channel_videos_bulk(videos: List[tuple]) -> List[str]:
    """
    Add multiple videos to channel_videos in a single batch.
    videos: [(channel_id, video_id, title, duration, is_short, upload_date), ...]
    Returns: list of video_ids that were newly added.
    """
    if not videos:
        return []
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Insert and return which ones were new
        new_ids = []
        for video in videos:
            result = await conn.fetchval(
                """INSERT INTO channel_videos (channel_id, video_id, title, duration, is_short, upload_date)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (video_id) DO NOTHING
                   RETURNING video_id""",
                *video
            )
            if result:
                new_ids.append(result)
        return new_ids


# ============ CACHING LAYER ============
# In-memory cache to reduce repeated DB queries

import time as _time

_settings_cache = {}
_settings_cache_ttl = 60  # seconds

_admin_cache = {}
_admin_cache_ttl = 300  # 5 minutes


async def get_user_settings_cached(user_id: int) -> Dict[str, Any]:
    """Get user settings with in-memory caching (60s TTL)."""
    cache_key = f"settings:{user_id}"
    now = _time.time()
    
    if cache_key in _settings_cache:
        data, timestamp = _settings_cache[cache_key]
        if now - timestamp < _settings_cache_ttl:
            return data
    
    # Fetch from DB and cache
    data = await get_user_settings(user_id)
    _settings_cache[cache_key] = (data, now)
    return data


def invalidate_settings_cache(user_id: int = None):
    """Invalidate settings cache for a user or all users."""
    if user_id:
        cache_key = f"settings:{user_id}"
        _settings_cache.pop(cache_key, None)
    else:
        _settings_cache.clear()


async def get_admin_setting_cached(key: str, default: str = None) -> str:
    """Get admin setting with in-memory caching (5 min TTL)."""
    now = _time.time()
    
    if key in _admin_cache:
        data, timestamp = _admin_cache[key]
        if now - timestamp < _admin_cache_ttl:
            return data
    
    # Fetch from DB and cache
    data = await get_admin_setting(key, default)
    _admin_cache[key] = (data, now)
    return data


def invalidate_admin_cache(key: str = None):
    """Invalidate admin cache for a key or all keys."""
    if key:
        _admin_cache.pop(key, None)
    else:
        _admin_cache.clear()


# ============ Statistics Operations ============

async def record_watch(user_id: int, channel_id: str, channel_name: str, 
                       duration: int, is_short: bool, is_lofi: bool = False) -> None:
    """Record a video watch for statistics."""
    today = date.today()
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Update daily stats with UPSERT
        await conn.execute("""
            INSERT INTO daily_stats (user_id, date, videos_watched, shorts_watched, 
                                     lofi_sessions, total_duration, lofi_duration)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id, date) DO UPDATE SET
                videos_watched = daily_stats.videos_watched + CASE WHEN $8 = FALSE AND $9 = FALSE THEN 1 ELSE 0 END,
                shorts_watched = daily_stats.shorts_watched + CASE WHEN $8 = TRUE THEN 1 ELSE 0 END,
                lofi_sessions = daily_stats.lofi_sessions + CASE WHEN $9 = TRUE THEN 1 ELSE 0 END,
                total_duration = daily_stats.total_duration + $6,
                lofi_duration = daily_stats.lofi_duration + CASE WHEN $9 = TRUE THEN $7 ELSE 0 END
        """, user_id, today, 
              0 if is_short or is_lofi else 1,  # videos_watched
              1 if is_short else 0,              # shorts_watched
              1 if is_lofi else 0,               # lofi_sessions
              duration,                           # total_duration
              duration if is_lofi else 0,        # lofi_duration
              is_short, is_lofi)
        
        # Update channel stats with UPSERT
        await conn.execute("""
            INSERT INTO channel_stats (user_id, channel_id, channel_name, 
                                       videos_watched, total_duration, last_watched)
            VALUES ($1, $2, $3, 1, $4, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, channel_id) DO UPDATE SET
                videos_watched = channel_stats.videos_watched + 1,
                total_duration = channel_stats.total_duration + $4,
                last_watched = CURRENT_TIMESTAMP,
                channel_name = $3
        """, user_id, channel_id, channel_name, duration)


async def get_daily_stats(user_id: int, target_date: date = None) -> Dict[str, Any]:
    """Get stats for a specific day."""
    if target_date is None:
        target_date = date.today()
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM daily_stats WHERE user_id = $1 AND date = $2",
            user_id, target_date
        )
        
        if row:
            return dict(row)
        
        return {
            "videos_watched": 0,
            "shorts_watched": 0,
            "lofi_sessions": 0,
            "total_duration": 0,
            "lofi_duration": 0
        }


async def get_weekly_stats(user_id: int) -> Dict[str, Any]:
    """Get aggregated stats for the past week."""
    week_ago = date.today() - timedelta(days=7)
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Aggregate daily stats
        row = await conn.fetchrow("""
            SELECT 
                COALESCE(SUM(videos_watched), 0) as videos_watched,
                COALESCE(SUM(shorts_watched), 0) as shorts_watched,
                COALESCE(SUM(lofi_sessions), 0) as lofi_sessions,
                COALESCE(SUM(total_duration), 0) as total_duration,
                COALESCE(SUM(lofi_duration), 0) as lofi_duration
            FROM daily_stats 
            WHERE user_id = $1 AND date >= $2
        """, user_id, week_ago)
        
        stats = dict(row)
        
        # Get top channels by time
        rows = await conn.fetch("""
            SELECT channel_id, channel_name, 
                   SUM(videos_watched) as videos,
                   SUM(total_duration) as duration
            FROM channel_stats 
            WHERE user_id = $1 AND last_watched >= $2
            GROUP BY channel_id, channel_name
            ORDER BY duration DESC
            LIMIT 5
        """, user_id, week_ago)
        
        stats["top_channels"] = [dict(row) for row in rows]
        
        return stats


async def get_all_time_stats(user_id: int) -> Dict[str, Any]:
    """Get all-time stats for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 
                COALESCE(SUM(videos_watched), 0) as videos_watched,
                COALESCE(SUM(shorts_watched), 0) as shorts_watched,
                COALESCE(SUM(lofi_sessions), 0) as lofi_sessions,
                COALESCE(SUM(total_duration), 0) as total_duration,
                COALESCE(SUM(lofi_duration), 0) as lofi_duration
            FROM daily_stats 
            WHERE user_id = $1
        """, user_id)
        
        return dict(row)


async def get_today_watch_count(user_id: int) -> int:
    """Get today's total video count for limit checking."""
    stats = await get_daily_stats(user_id)
    return stats["videos_watched"] + stats["shorts_watched"]


# ============ Favorites Operations ============

async def add_favorite(user_id: int, video_id: str, video_url: str, title: str,
                       channel_name: str, duration: int, thumbnail_url: str = None) -> bool:
    """Add video to favorites. Returns True if added, False if already exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO favorites 
                   (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                user_id, video_id, video_url, title, channel_name, duration, thumbnail_url
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def remove_favorite(user_id: int, video_id: str) -> bool:
    """Remove video from favorites."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM favorites WHERE user_id = $1 AND video_id = $2",
            user_id, video_id
        )
        return result.split()[-1] != '0'


async def get_favorites(user_id: int) -> List[Dict[str, Any]]:
    """Get all favorite videos for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM favorites WHERE user_id = $1 ORDER BY added_at DESC",
            user_id
        )
        return [dict(row) for row in rows]


# ============ Export/Import Operations ============

async def export_user_data(user_id: int) -> Dict[str, Any]:
    """Export all user data as dictionary."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get user info
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        user = dict(row) if row else {}
        
        # Get settings
        settings = await get_user_settings(user_id)
        
        # Get subscriptions
        subscriptions = await get_subscriptions(user_id)
        
        # Get favorites
        favorites = await get_favorites(user_id)
        
        # Get queue
        queue = await get_queue(user_id)
        
        return {
            "exported_at": datetime.now().isoformat(),
            "user": user,
            "settings": settings,
            "subscriptions": subscriptions,
            "favorites": favorites,
            "queue": queue
        }


async def import_user_data(user_id: int, data: Dict[str, Any]) -> Dict[str, int]:
    """Import user data from dictionary. Returns counts of imported items."""
    counts = {"subscriptions": 0, "favorites": 0, "queue": 0}
    
    # Import settings
    if "settings" in data:
        settings = data["settings"].copy()
        settings.pop("user_id", None)  # Remove user_id from settings
        await update_user_settings(user_id, **settings)
    
    # Import subscriptions
    for sub in data.get("subscriptions", []):
        if await add_subscription(
            user_id, sub["channel_id"], sub["channel_name"],
            sub["channel_url"], sub.get("is_priority", False)
        ):
            counts["subscriptions"] += 1
            if sub.get("nickname"):
                await set_channel_nickname(user_id, sub["channel_id"], sub["nickname"])
    
    # Import favorites
    for fav in data.get("favorites", []):
        if await add_favorite(
            user_id, fav["video_id"], fav["video_url"], fav["title"],
            fav["channel_name"], fav["duration"], fav.get("thumbnail_url")
        ):
            counts["favorites"] += 1
    
    # Import queue
    for item in data.get("queue", []):
        if await add_to_queue(
            user_id, item["video_id"], item["video_url"], item["title"],
            item["channel_name"], item["duration"], item.get("thumbnail_url")
        ):
            counts["queue"] += 1
    
    return counts
