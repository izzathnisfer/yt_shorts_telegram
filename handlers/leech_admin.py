"""
Comprehensive Admin Panel - Full bot monitoring and management.
Provides unified view of all bot activities (YT + Leech).
"""

import os
import time
import logging
import psutil
from typing import Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import DOWNLOADS_PATH
from database import get_pool
from services.leech_data import get_all_leech_users, get_leech_stats

logger = logging.getLogger(__name__)

# Admin user IDs
_admin_users: Optional[tuple] = None
_bot_start_time = time.time()


def _load_admin_users() -> tuple:
    """Load admin users from environment."""
    global _admin_users
    if _admin_users is None:
        admin_str = os.getenv("ADMIN_USERS", "")
        if admin_str:
            try:
                _admin_users = tuple(int(u.strip()) for u in admin_str.split(",") if u.strip())
            except ValueError:
                _admin_users = ()
        else:
            _admin_users = ()
    return _admin_users


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in _load_admin_users()


def humanbytes(size: float) -> str:
    """Convert bytes to human readable format."""
    if not size:
        return "0B"
    power = 1024
    t_n = 0
    power_dict = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size >= power and t_n < len(power_dict) - 1:
        size /= power
        t_n += 1
    return f"{size:.2f} {power_dict[t_n]}"


def get_readable_time(seconds: int) -> str:
    """Convert seconds to readable time string."""
    result = ""
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        result += f"{days}d "
    if hours > 0:
        result += f"{hours}h "
    if minutes > 0:
        result += f"{minutes}m "
    if seconds > 0 or not result:
        result += f"{seconds}s"
    return result.strip()


def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Build admin panel main menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Bot Summary", callback_data="admin:summary"),
            InlineKeyboardButton("🖥️ System", callback_data="admin:system"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin:users"),
            InlineKeyboardButton("📺 Subscriptions", callback_data="admin:subs"),
        ],
        [
            InlineKeyboardButton("📋 Active Tasks", callback_data="admin:tasks"),
            InlineKeyboardButton("📈 Leech Stats", callback_data="admin:leech"),
        ],
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="admin:notif"),
            InlineKeyboardButton("💾 Storage", callback_data="admin:storage"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
        ],
        [InlineKeyboardButton("❌ Close", callback_data="admin:close")],
    ])


async def _get_bot_summary() -> str:
    """Get comprehensive bot summary."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # User stats
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            
            # Check if video_history exists and get stats
            try:
                active_users = await conn.fetchval(
                    "SELECT COUNT(DISTINCT user_id) FROM video_history WHERE watched_at > NOW() - INTERVAL '7 days'"
                ) or 0
                total_videos = await conn.fetchval("SELECT COUNT(*) FROM video_history") or 0
                total_duration = await conn.fetchval(
                    "SELECT COALESCE(SUM(duration), 0) FROM video_history"
                ) or 0
            except Exception:
                active_users = 0
                total_videos = 0
                total_duration = 0
            
            # Subscription stats
            try:
                sub_count = await conn.fetchval("SELECT COUNT(*) FROM subscriptions") or 0
            except Exception:
                sub_count = 0
            
            # Queue stats
            try:
                queue_count = await conn.fetchval("SELECT COUNT(*) FROM queue") or 0
            except Exception:
                queue_count = 0
            
            # Favorites
            try:
                fav_count = await conn.fetchval("SELECT COUNT(*) FROM favorites") or 0
            except Exception:
                fav_count = 0
        
        # Leech stats
        try:
            leech_stats = await get_leech_stats()
            leech_total = leech_stats.get('total_tasks', 0)
            leech_data = humanbytes(leech_stats.get('total_bytes', 0))
        except Exception:
            leech_total = 0
            leech_data = "0B"
        
        uptime = get_readable_time(int(time.time() - _bot_start_time))
        hours_watched = total_duration // 3600
        
        return (
            "📊 **Bot Summary**\n\n"
            f"**Users:**\n"
            f"├ Total: {user_count}\n"
            f"├ Active (7d): {active_users}\n"
            f"└ Subscriptions: {sub_count}\n\n"
            f"**Content:**\n"
            f"├ Videos watched: {total_videos}\n"
            f"├ Watch time: {hours_watched}h\n"
            f"├ Queue items: {queue_count}\n"
            f"└ Favorites: {fav_count}\n\n"
            f"**Leech:**\n"
            f"├ Total tasks: {leech_total}\n"
            f"└ Data transferred: {leech_data}\n\n"
            f"**Uptime:** {uptime}"
        )
    except Exception as e:
        logger.error(f"Error getting bot summary: {e}")
        return f"❌ Error getting bot summary: {e}"


async def _get_system_status() -> str:
    """Get detailed system status."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(DOWNLOADS_PATH))
        
        return (
            "🖥️ **System Status**\n\n"
            f"**CPU:** {cpu}%\n"
            f"**RAM:** {mem.percent}% ({humanbytes(mem.used)}/{humanbytes(mem.total)})\n"
            f"**Disk:** {disk.percent}% ({humanbytes(disk.free)} free)\n"
            f"**Uptime:** {get_readable_time(int(time.time() - _bot_start_time))}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


async def _get_user_stats() -> str:
    """Get user statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_today = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM video_history WHERE DATE(watched_at) = CURRENT_DATE"
        )
        active_week = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM video_history WHERE watched_at > NOW() - INTERVAL '7 days'"
        )
        
        # Top users by watch time
        top_users = await conn.fetch("""
            SELECT u.username, u.first_name, u.user_id, 
                   COALESCE(SUM(vh.duration), 0) as total_duration,
                   COUNT(vh.id) as video_count
            FROM users u
            LEFT JOIN video_history vh ON u.user_id = vh.user_id
            GROUP BY u.user_id, u.username, u.first_name
            ORDER BY total_duration DESC
            LIMIT 5
        """)
    
    text = (
        f"👥 **User Statistics**\n\n"
        f"**Total Users:** {total}\n"
        f"**Active Today:** {active_today}\n"
        f"**Active (7d):** {active_week}\n\n"
        f"**Top Users (by watch time):**\n"
    )
    
    for i, u in enumerate(top_users, 1):
        name = u['username'] or u['first_name'] or str(u['user_id'])
        hours = u['total_duration'] // 3600
        text += f"{i}. {name[:15]} - {u['video_count']} videos ({hours}h)\n"
    
    return text


async def _get_subscription_stats() -> str:
    """Get subscription statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM subscriptions")
        unique_channels = await conn.fetchval(
            "SELECT COUNT(DISTINCT channel_id) FROM subscriptions"
        )
        
        # Most subscribed channels
        top_channels = await conn.fetch("""
            SELECT channel_name, COUNT(*) as sub_count
            FROM subscriptions
            GROUP BY channel_name
            ORDER BY sub_count DESC
            LIMIT 5
        """)
    
    text = (
        f"📺 **Subscription Statistics**\n\n"
        f"**Total Subscriptions:** {total}\n"
        f"**Unique Channels:** {unique_channels}\n\n"
        f"**Most Subscribed:**\n"
    )
    
    for i, ch in enumerate(top_channels, 1):
        text += f"{i}. {ch['channel_name'][:20]} ({ch['sub_count']} subs)\n"
    
    return text


async def _get_storage_info() -> str:
    """Get storage information."""
    try:
        disk = psutil.disk_usage(str(DOWNLOADS_PATH))
        download_files = list(DOWNLOADS_PATH.glob("*"))
        file_count = len([f for f in download_files if f.is_file()])
        total_size = sum(f.stat().st_size for f in download_files if f.is_file())
        
        return (
            "💾 **Storage**\n\n"
            f"**Downloads:**\n"
            f"├ Files: {file_count}\n"
            f"└ Size: {humanbytes(total_size)}\n\n"
            f"**Disk:**\n"
            f"├ Used: {humanbytes(disk.used)} ({disk.percent}%)\n"
            f"└ Free: {humanbytes(disk.free)}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    await update.message.reply_text(
        "🔧 **Admin Panel**\n\nSelect an option:",
        parse_mode='Markdown',
        reply_markup=_admin_menu_keyboard()
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callbacks."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("Unauthorized", show_alert=True)
        return
    
    await query.answer()
    data = query.data
    
    back_refresh = lambda d: InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data=d)],
        [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
    ])
    
    if data == "admin:close":
        await query.message.delete()
    
    elif data == "admin:menu":
        await query.message.edit_text(
            "🔧 **Admin Panel**\n\nSelect an option:",
            parse_mode='Markdown',
            reply_markup=_admin_menu_keyboard()
        )
    
    elif data == "admin:summary":
        text = await _get_bot_summary()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:system":
        text = await _get_system_status()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:users":
        text = await _get_user_stats()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:subs":
        text = await _get_subscription_stats()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:tasks":
        from handlers.leech import get_active_tasks
        tasks = get_active_tasks()
        
        if not tasks:
            text = "📋 **Active Tasks**\n\n_No active tasks._"
        else:
            text = f"📋 **Active Tasks** ({len(tasks)})\n\n"
            for (uid, tid), info in list(tasks.items())[:5]:
                text += f"• User `{uid}`: {info.get('file_name', 'Unknown')[:20]}... ({info.get('progress', 0):.0f}%)\n"
        
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:leech":
        try:
            stats = await get_leech_stats()
            text = (
                "📈 **Leech Statistics**\n\n"
                f"**All Time:**\n"
                f"├ Total: {stats['total_tasks']}\n"
                f"├ Completed: {stats['completed']}\n"
                f"├ Failed: {stats['failed']}\n"
                f"└ Data: {humanbytes(stats['total_bytes'])}\n\n"
                f"**Today:**\n"
                f"├ Tasks: {stats['today_tasks']}\n"
                f"└ Data: {humanbytes(stats['today_bytes'])}"
            )
        except Exception as e:
            text = f"❌ Error: {e}"
        
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh(data))
    
    elif data == "admin:storage":
        text = await _get_storage_info()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧹 Clean Old Files", callback_data="admin:clean")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin:storage")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
        ])
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    elif data == "admin:clean":
        cleaned = 0
        for f in DOWNLOADS_PATH.glob("*"):
            if f.is_file() and (time.time() - f.stat().st_mtime) > 3600:
                try:
                    f.unlink()
                    cleaned += 1
                except:
                    pass
        await query.answer(f"🧹 Cleaned {cleaned} files", show_alert=True)
        # Refresh storage view
        text = await _get_storage_info()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=back_refresh("admin:storage"))
    
    elif data == "admin:broadcast":
        context.user_data['admin_broadcast'] = True
        await query.message.edit_text(
            "📢 **Broadcast Message**\n\n"
            "Send the message you want to broadcast to all users.\n"
            "Use `/cancel` to cancel.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="admin:menu")]
            ])
        )
    
    elif data == "admin:notif":
        text = await _get_notification_stats()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=_notif_config_keyboard())
    
    elif data.startswith("admin:interval:"):
        # Set check interval
        interval = data.split(":")[2]
        from database import set_admin_setting
        await set_admin_setting('check_interval_minutes', interval)
        await query.answer(f"✅ Check interval set to {interval} minutes", show_alert=True)
        text = await _get_notification_stats()
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=_notif_config_keyboard())


def _notif_config_keyboard() -> InlineKeyboardMarkup:
    """Build notification config keyboard with interval options."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5m", callback_data="admin:interval:5"),
            InlineKeyboardButton("10m", callback_data="admin:interval:10"),
            InlineKeyboardButton("15m", callback_data="admin:interval:15"),
        ],
        [
            InlineKeyboardButton("30m", callback_data="admin:interval:30"),
            InlineKeyboardButton("60m", callback_data="admin:interval:60"),
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin:notif")],
        [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
    ])


async def _get_notification_stats() -> str:
    """Get notification statistics and settings."""
    from database import get_admin_setting
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Get notification stats
        total_sent = await conn.fetchval("SELECT COUNT(*) FROM notification_log")
        today_sent = await conn.fetchval(
            "SELECT COUNT(*) FROM notification_log WHERE DATE(sent_at) = CURRENT_DATE"
        )
        pending_snoozes = await conn.fetchval(
            "SELECT COUNT(*) FROM snoozed_notifications WHERE status = 'pending'"
        )
        total_channel_videos = await conn.fetchval("SELECT COUNT(*) FROM channel_videos")
    
    # Get current check interval
    check_interval = await get_admin_setting('check_interval_minutes', '15')
    
    return (
        "🔔 **Notification Settings**\n\n"
        f"**Current Check Interval:** {check_interval} mins\n\n"
        f"**Stats:**\n"
        f"├ Total notifications sent: {total_sent}\n"
        f"├ Sent today: {today_sent}\n"
        f"├ Pending snoozes: {pending_snoozes}\n"
        f"└ Videos tracked: {total_channel_videos}\n\n"
        "**Set Check Interval:**"
    )


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle broadcast message from admin. Returns True if handled."""
    if not context.user_data.get('admin_broadcast'):
        return False
    
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return False
    
    context.user_data['admin_broadcast'] = False
    message_text = update.message.text
    
    if message_text == '/cancel':
        await update.message.reply_text("❌ Broadcast cancelled.")
        return True
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE is_active = TRUE")
    
    sent = 0
    failed = 0
    
    status = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=f"📢 **Announcement**\n\n{message_text}",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            failed += 1
    
    await status.edit_text(f"✅ Broadcast complete!\n\nSent: {sent}\nFailed: {failed}")
    return True
