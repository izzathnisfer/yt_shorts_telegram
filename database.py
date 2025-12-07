"""
Database operations for YouTube Shorts Bot.
Uses async SQLite for non-blocking operations.
Handles all user data, subscriptions, queue, and statistics.
"""

import aiosqlite
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from config import DATABASE_PATH, DEFAULT_CHECK_INTERVAL, DEFAULT_RESOLUTION, DEFAULT_DAILY_LIMIT
from config import DEFAULT_QUIET_START, DEFAULT_QUIET_END, DEFAULT_TIMEZONE


async def init_db():
    """Initialize database with all required tables."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        db.row_factory = aiosqlite.Row
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # User settings
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                daily_limit INTEGER DEFAULT {DEFAULT_DAILY_LIMIT},
                check_interval INTEGER DEFAULT {DEFAULT_CHECK_INTERVAL},
                resolution TEXT DEFAULT '{DEFAULT_RESOLUTION}',
                quiet_start TEXT DEFAULT '{DEFAULT_QUIET_START}',
                quiet_end TEXT DEFAULT '{DEFAULT_QUIET_END}',
                auto_download_shorts BOOLEAN DEFAULT 1,
                focus_until TIMESTAMP,
                timezone TEXT DEFAULT '{DEFAULT_TIMEZONE}',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Channel subscriptions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                channel_url TEXT,
                nickname TEXT,
                is_priority BOOLEAN DEFAULT 0,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, channel_id)
            )
        """)
        
        # Watch queue
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_id TEXT,
                video_url TEXT,
                title TEXT,
                channel_name TEXT,
                duration INTEGER,
                thumbnail_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_downloaded BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        # Video history (for duplicate detection & stats)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS video_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_id TEXT,
                title TEXT,
                channel_id TEXT,
                channel_name TEXT,
                duration INTEGER,
                is_short BOOLEAN,
                is_lofi BOOLEAN DEFAULT 0,
                watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        # Daily stats
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        
        # Seen videos (for new video detection in subscriptions)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_id TEXT,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, video_id)
            )
        """)
        
        await db.commit()


# ============ User Operations ============

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
    """Get existing user or create new one with default settings."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        user = await cursor.fetchone()
        
        if user:
            return dict(user)
        
        # Create new user
        await db.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        
        # Create default settings
        await db.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)",
            (user_id,)
        )
        
        await db.commit()
        
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "is_active": True
        }


async def get_all_active_users() -> List[Dict[str, Any]]:
    """Get all active users for scheduled tasks."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ============ Settings Operations ============

async def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Get user settings."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return dict(row)
        
        # Create default settings if not exists
        await db.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()
        
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
    
    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [user_id]
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            f"UPDATE user_settings SET {set_clause} WHERE user_id = ?",
            values
        )
        await db.commit()


async def set_focus_mode(user_id: int, until: Optional[datetime]) -> None:
    """Set or clear focus mode for user."""
    await update_user_settings(user_id, focus_until=until.isoformat() if until else None)


async def is_in_focus_mode(user_id: int) -> tuple[bool, Optional[datetime]]:
    """Check if user is in focus mode and return end time."""
    settings = await get_user_settings(user_id)
    focus_until = settings.get("focus_until")
    
    if not focus_until:
        return False, None
    
    end_time = datetime.fromisoformat(focus_until)
    if end_time <= datetime.now():
        # Focus mode expired, clear it
        await set_focus_mode(user_id, None)
        return False, None
    
    return True, end_time


# ============ Subscription Operations ============

async def add_subscription(user_id: int, channel_id: str, channel_name: str, 
                          channel_url: str, is_priority: bool = False) -> bool:
    """Add a channel subscription. Returns True if added, False if already exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                """INSERT INTO subscriptions 
                   (user_id, channel_id, channel_name, channel_url, is_priority)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, channel_id, channel_name, channel_url, is_priority)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_subscription(user_id: int, channel_id: str) -> bool:
    """Remove a channel subscription."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM subscriptions WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_subscriptions(user_id: int) -> List[Dict[str, Any]]:
    """Get all subscriptions for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM subscriptions 
               WHERE user_id = ? 
               ORDER BY is_priority DESC, channel_name ASC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_subscription(user_id: int, channel_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific subscription."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_channel_priority(user_id: int, channel_id: str, is_priority: bool) -> None:
    """Toggle priority status for a channel."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE subscriptions SET is_priority = ? WHERE user_id = ? AND channel_id = ?",
            (is_priority, user_id, channel_id)
        )
        await db.commit()


async def set_channel_nickname(user_id: int, channel_id: str, nickname: Optional[str]) -> None:
    """Set a custom nickname for a channel."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE subscriptions SET nickname = ? WHERE user_id = ? AND channel_id = ?",
            (nickname, user_id, channel_id)
        )
        await db.commit()


# ============ Queue Operations ============

async def add_to_queue(user_id: int, video_id: str, video_url: str, title: str,
                       channel_name: str, duration: int, thumbnail_url: str = None) -> bool:
    """Add video to watch queue. Returns True if added, False if already exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                """INSERT INTO queue 
                   (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_from_queue(user_id: int, video_id: str) -> bool:
    """Remove video from queue."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM queue WHERE user_id = ? AND video_id = ?",
            (user_id, video_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_queue(user_id: int) -> List[Dict[str, Any]]:
    """Get all queued videos for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM queue WHERE user_id = ? ORDER BY added_at ASC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def clear_queue(user_id: int) -> int:
    """Clear all queued videos. Returns count of removed items."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM queue WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
        return cursor.rowcount


async def mark_queue_downloaded(user_id: int, video_id: str) -> None:
    """Mark a queued video as downloaded."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE queue SET is_downloaded = 1 WHERE user_id = ? AND video_id = ?",
            (user_id, video_id)
        )
        await db.commit()


# ============ Video History & Duplicate Detection ============

async def add_to_history(user_id: int, video_id: str, title: str, channel_id: str,
                         channel_name: str, duration: int, is_short: bool,
                         is_lofi: bool = False, source: str = "direct") -> bool:
    """Add video to history. Returns True if new, False if duplicate."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                """INSERT INTO video_history 
                   (user_id, video_id, title, channel_id, channel_name, duration, is_short, is_lofi, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, video_id, title, channel_id, channel_name, duration, is_short, is_lofi, source)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def check_duplicate(user_id: int, video_id: str) -> Optional[Dict[str, Any]]:
    """Check if video was already downloaded. Returns history entry if exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM video_history WHERE user_id = ? AND video_id = ?",
            (user_id, video_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def mark_video_seen(user_id: int, video_id: str) -> None:
    """Mark a video as seen (for subscription new video detection)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO seen_videos (user_id, video_id) VALUES (?, ?)",
            (user_id, video_id)
        )
        await db.commit()


async def is_video_seen(user_id: int, video_id: str) -> bool:
    """Check if a video has been seen by user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT 1 FROM seen_videos WHERE user_id = ? AND video_id = ?",
            (user_id, video_id)
        )
        return await cursor.fetchone() is not None


# ============ Statistics Operations ============

async def record_watch(user_id: int, channel_id: str, channel_name: str, 
                       duration: int, is_short: bool, is_lofi: bool = False) -> None:
    """Record a video watch for statistics."""
    today = date.today().isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Update daily stats
        await db.execute("""
            INSERT INTO daily_stats (user_id, date, videos_watched, shorts_watched, 
                                     lofi_sessions, total_duration, lofi_duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                videos_watched = videos_watched + CASE WHEN ? = 0 AND ? = 0 THEN 1 ELSE 0 END,
                shorts_watched = shorts_watched + CASE WHEN ? = 1 THEN 1 ELSE 0 END,
                lofi_sessions = lofi_sessions + CASE WHEN ? = 1 THEN 1 ELSE 0 END,
                total_duration = total_duration + ?,
                lofi_duration = lofi_duration + CASE WHEN ? = 1 THEN ? ELSE 0 END
        """, (user_id, today, 
              0 if is_short or is_lofi else 1,  # videos_watched
              1 if is_short else 0,              # shorts_watched
              1 if is_lofi else 0,               # lofi_sessions
              duration,                           # total_duration
              duration if is_lofi else 0,        # lofi_duration
              is_short, is_lofi,                 # for UPDATE conditions
              is_short, is_lofi, duration, is_lofi, duration))
        
        # Update channel stats
        await db.execute("""
            INSERT INTO channel_stats (user_id, channel_id, channel_name, 
                                       videos_watched, total_duration, last_watched)
            VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                videos_watched = videos_watched + 1,
                total_duration = total_duration + ?,
                last_watched = CURRENT_TIMESTAMP,
                channel_name = ?
        """, (user_id, channel_id, channel_name, duration, duration, channel_name))
        
        await db.commit()


async def get_daily_stats(user_id: int, target_date: date = None) -> Dict[str, Any]:
    """Get stats for a specific day."""
    if target_date is None:
        target_date = date.today()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM daily_stats WHERE user_id = ? AND date = ?",
            (user_id, target_date.isoformat())
        )
        row = await cursor.fetchone()
        
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
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Aggregate daily stats
        cursor = await db.execute("""
            SELECT 
                COALESCE(SUM(videos_watched), 0) as videos_watched,
                COALESCE(SUM(shorts_watched), 0) as shorts_watched,
                COALESCE(SUM(lofi_sessions), 0) as lofi_sessions,
                COALESCE(SUM(total_duration), 0) as total_duration,
                COALESCE(SUM(lofi_duration), 0) as lofi_duration
            FROM daily_stats 
            WHERE user_id = ? AND date >= ?
        """, (user_id, week_ago))
        
        stats = dict(await cursor.fetchone())
        
        # Get top channels by time
        cursor = await db.execute("""
            SELECT channel_id, channel_name, 
                   SUM(videos_watched) as videos,
                   SUM(total_duration) as duration
            FROM channel_stats 
            WHERE user_id = ? AND last_watched >= ?
            GROUP BY channel_id
            ORDER BY duration DESC
            LIMIT 5
        """, (user_id, week_ago))
        
        stats["top_channels"] = [dict(row) for row in await cursor.fetchall()]
        
        return stats


async def get_all_time_stats(user_id: int) -> Dict[str, Any]:
    """Get all-time stats for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT 
                COALESCE(SUM(videos_watched), 0) as videos_watched,
                COALESCE(SUM(shorts_watched), 0) as shorts_watched,
                COALESCE(SUM(lofi_sessions), 0) as lofi_sessions,
                COALESCE(SUM(total_duration), 0) as total_duration,
                COALESCE(SUM(lofi_duration), 0) as lofi_duration
            FROM daily_stats 
            WHERE user_id = ?
        """, (user_id,))
        
        return dict(await cursor.fetchone())


async def get_today_watch_count(user_id: int) -> int:
    """Get today's total video count for limit checking."""
    stats = await get_daily_stats(user_id)
    return stats["videos_watched"] + stats["shorts_watched"]


# ============ Favorites Operations ============

async def add_favorite(user_id: int, video_id: str, video_url: str, title: str,
                       channel_name: str, duration: int, thumbnail_url: str = None) -> bool:
    """Add video to favorites. Returns True if added, False if already exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                """INSERT INTO favorites 
                   (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, video_id, video_url, title, channel_name, duration, thumbnail_url)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_favorite(user_id: int, video_id: str) -> bool:
    """Remove video from favorites."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND video_id = ?",
            (user_id, video_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_favorites(user_id: int) -> List[Dict[str, Any]]:
    """Get all favorite videos for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM favorites WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ============ Export/Import Operations ============

async def export_user_data(user_id: int) -> Dict[str, Any]:
    """Export all user data as dictionary."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get user info
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = dict(await cursor.fetchone()) if (await cursor.fetchone()) else {}
        
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
        settings = data["settings"]
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
