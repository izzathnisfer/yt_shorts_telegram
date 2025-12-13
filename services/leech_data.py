"""
Leech user data persistence using PostgreSQL.
Stores Nextcloud credentials with base64 encoding for basic obfuscation.
"""

import base64
import logging
from typing import Dict, Any, Optional

from database import get_pool

logger = logging.getLogger(__name__)

# Constants
DEFAULT_NC_DELETE_TIMER = 30


def _encode(value: str) -> str:
    """Encode a string for storage (basic obfuscation)."""
    if not value or value == 'NOTSET':
        return value
    return base64.b64encode(value.encode()).decode()


def _decode(value: str) -> str:
    """Decode a stored string."""
    if not value or value == 'NOTSET':
        return value
    try:
        return base64.b64decode(value.encode()).decode()
    except Exception:
        return value


async def init_leech_tables() -> None:
    """Initialize leech-related database tables."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leech_settings (
                user_id BIGINT PRIMARY KEY,
                nc_url TEXT DEFAULT 'NOTSET',
                nc_username TEXT DEFAULT 'NOTSET',
                nc_password TEXT DEFAULT 'NOTSET',
                nc_auto_delete BOOLEAN DEFAULT TRUE,
                nc_delete_timer INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Leech task history for admin monitoring
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leech_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                file_name TEXT,
                file_size BIGINT,
                upload_target TEXT,
                status TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        logger.info("Leech database tables initialized")


async def get_nc_settings(user_id: int) -> Dict[str, Any]:
    """Get Nextcloud settings for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leech_settings WHERE user_id = $1", user_id
        )
        
        if row:
            return {
                "link": _decode(row['nc_url']),
                "user_name": _decode(row['nc_username']),
                "password": _decode(row['nc_password']),
                "nc_auto_delete": row['nc_auto_delete'],
                "nc_delete_timer": row['nc_delete_timer']
            }
        
        # Return defaults
        return {
            "link": "NOTSET",
            "user_name": "NOTSET",
            "password": "NOTSET",
            "nc_auto_delete": True,
            "nc_delete_timer": DEFAULT_NC_DELETE_TIMER
        }


async def initialize_user(user_id: int) -> Dict[str, Any]:
    """Initialize user with default Nextcloud settings."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check if exists
        row = await conn.fetchrow(
            "SELECT 1 FROM leech_settings WHERE user_id = $1", user_id
        )
        
        if not row:
            await conn.execute("""
                INSERT INTO leech_settings (user_id)
                VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)
    
    return await get_nc_settings(user_id)


async def update_nc_setting(user_id: int, key: str, value: Any) -> None:
    """Update a single Nextcloud setting for a user."""
    # Map friendly keys to database columns
    key_map = {
        'link': 'nc_url',
        'user_name': 'nc_username',
        'password': 'nc_password',
        'nc_auto_delete': 'nc_auto_delete',
        'nc_delete_timer': 'nc_delete_timer'
    }
    
    db_key = key_map.get(key, key)
    
    # Encode sensitive fields
    if key in ['link', 'user_name', 'password']:
        value = _encode(value)
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure user exists in leech_settings
        await conn.execute("""
            INSERT INTO leech_settings (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id)
        
        # Update specific field
        await conn.execute(f"""
            UPDATE leech_settings 
            SET {db_key} = $1, updated_at = CURRENT_TIMESTAMP 
            WHERE user_id = $2
        """, value, user_id)


async def is_nc_configured(user_id: int) -> bool:
    """Check if user has Nextcloud fully configured."""
    settings = await get_nc_settings(user_id)
    required = ['link', 'user_name', 'password']
    return all(settings.get(k) and settings[k] != 'NOTSET' for k in required)


async def get_all_leech_users() -> list:
    """Get all users with leech settings (for admin)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ls.user_id, ls.nc_auto_delete, ls.nc_delete_timer,
                   ls.nc_url, ls.nc_username,
                   u.username, u.first_name
            FROM leech_settings ls
            LEFT JOIN users u ON ls.user_id = u.user_id
            ORDER BY ls.updated_at DESC
        """)
        
        result = []
        for row in rows:
            nc_configured = (
                row['nc_url'] != 'NOTSET' and 
                row['nc_username'] != 'NOTSET'
            )
            result.append({
                'user_id': row['user_id'],
                'username': row['username'] or row['first_name'] or str(row['user_id']),
                'nc_configured': nc_configured,
                'nc_auto_delete': row['nc_auto_delete'],
                'nc_delete_timer': row['nc_delete_timer']
            })
        
        return result


# ============ Leech History (for admin monitoring) ============

async def record_leech_start(user_id: int, file_name: str, upload_target: str) -> int:
    """Record start of a leech task. Returns task ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO leech_history (user_id, file_name, upload_target, status)
            VALUES ($1, $2, $3, 'downloading')
            RETURNING id
        """, user_id, file_name, upload_target)
        return row['id']


async def update_leech_status(task_id: int, status: str, file_size: int = None, 
                               error_message: str = None) -> None:
    """Update leech task status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status in ('completed', 'failed', 'cancelled'):
            await conn.execute("""
                UPDATE leech_history
                SET status = $1, file_size = COALESCE($2, file_size),
                    error_message = $3, completed_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """, status, file_size, error_message, task_id)
        else:
            await conn.execute("""
                UPDATE leech_history
                SET status = $1, file_size = COALESCE($2, file_size)
                WHERE id = $3
            """, status, file_size, task_id)


async def get_leech_stats() -> Dict[str, Any]:
    """Get leech statistics for admin panel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Total counts
        row = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_tasks,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled,
                COALESCE(SUM(file_size), 0) as total_bytes
            FROM leech_history
        """)
        
        # Today's stats
        today_row = await conn.fetchrow("""
            SELECT 
                COUNT(*) as today_tasks,
                COALESCE(SUM(file_size), 0) as today_bytes
            FROM leech_history
            WHERE DATE(started_at) = CURRENT_DATE
        """)
        
        # Recent tasks
        recent = await conn.fetch("""
            SELECT lh.*, u.username, u.first_name
            FROM leech_history lh
            LEFT JOIN users u ON lh.user_id = u.user_id
            ORDER BY lh.started_at DESC
            LIMIT 10
        """)
        
        return {
            'total_tasks': row['total_tasks'],
            'completed': row['completed'],
            'failed': row['failed'],
            'cancelled': row['cancelled'],
            'total_bytes': row['total_bytes'],
            'today_tasks': today_row['today_tasks'],
            'today_bytes': today_row['today_bytes'],
            'recent': [dict(r) for r in recent]
        }
