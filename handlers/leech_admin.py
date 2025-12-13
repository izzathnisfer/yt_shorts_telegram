"""
Advanced Admin panel handler for LeechBot features.
Provides comprehensive monitoring and management capabilities.
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
from services.leech_data import (
    get_all_leech_users, get_nc_settings, update_nc_setting, 
    get_leech_stats, DEFAULT_NC_DELETE_TIMER
)
from handlers.leech import get_active_tasks, get_task, humanbytes, get_readable_time

logger = logging.getLogger(__name__)

# Admin user IDs - loaded from env
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


def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Build admin panel main menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Active Tasks", callback_data="admin:tasks"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin:stats"),
        ],
        [
            InlineKeyboardButton("📜 Task History", callback_data="admin:history"),
            InlineKeyboardButton("👥 Users", callback_data="admin:users"),
        ],
        [
            InlineKeyboardButton("🖥️ System Status", callback_data="admin:status"),
            InlineKeyboardButton("💾 Storage", callback_data="admin:storage"),
        ],
        [InlineKeyboardButton("❌ Close", callback_data="admin:close")],
    ])


def _get_system_status_detailed() -> str:
    """Get detailed system status."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(DOWNLOADS_PATH))
        uptime = get_readable_time(int(time.time() - _bot_start_time))
        
        # Network I/O
        net = psutil.net_io_counters()
        
        # Load average (if available)
        try:
            load = os.getloadavg()
            load_str = f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}"
        except (AttributeError, OSError):
            load_str = "N/A"
        
        active_tasks = get_active_tasks()
        
        return (
            "🖥️ **System Status**\n\n"
            f"**CPU Usage:** {cpu}%\n"
            f"**Load Average:** {load_str}\n\n"
            f"**RAM:** {mem.percent}%\n"
            f"├ Used: {humanbytes(mem.used)}\n"
            f"├ Free: {humanbytes(mem.available)}\n"
            f"└ Total: {humanbytes(mem.total)}\n\n"
            f"**Disk:** {disk.percent}%\n"
            f"├ Used: {humanbytes(disk.used)}\n"
            f"├ Free: {humanbytes(disk.free)}\n"
            f"└ Total: {humanbytes(disk.total)}\n\n"
            f"**Network I/O:**\n"
            f"├ Sent: {humanbytes(net.bytes_sent)}\n"
            f"└ Recv: {humanbytes(net.bytes_recv)}\n\n"
            f"**Bot Uptime:** {uptime}\n"
            f"**Active Tasks:** {len(active_tasks)}"
        )
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return "❌ Error getting system status."


async def _get_storage_info() -> str:
    """Get detailed storage information."""
    try:
        disk = psutil.disk_usage(str(DOWNLOADS_PATH))
        
        # Count files in downloads
        download_files = list(DOWNLOADS_PATH.glob("*"))
        file_count = len([f for f in download_files if f.is_file()])
        total_download_size = sum(f.stat().st_size for f in download_files if f.is_file())
        
        return (
            "💾 **Storage Information**\n\n"
            f"**Downloads Directory:**\n"
            f"├ Path: `{DOWNLOADS_PATH}`\n"
            f"├ Files: {file_count}\n"
            f"└ Size: {humanbytes(total_download_size)}\n\n"
            f"**Disk Usage:**\n"
            f"├ Used: {humanbytes(disk.used)} ({disk.percent}%)\n"
            f"├ Free: {humanbytes(disk.free)}\n"
            f"└ Total: {humanbytes(disk.total)}"
        )
    except Exception as e:
        logger.error(f"Error getting storage info: {e}")
        return "❌ Error getting storage information."


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command - Open advanced admin panel."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not an admin.")
        return
    
    active_tasks = get_active_tasks()
    
    await update.message.reply_text(
        "🔧 **Admin Control Panel**\n\n"
        f"📋 Active Tasks: **{len(active_tasks)}**\n"
        f"⏱️ Uptime: {get_readable_time(int(time.time() - _bot_start_time))}\n\n"
        "Select an option below:",
        parse_mode='Markdown',
        reply_markup=_admin_menu_keyboard()
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callbacks."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("You are not an admin.", show_alert=True)
        return
    
    await query.answer()
    data = query.data
    
    back_button = [[InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]]
    refresh_back = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=data)],
        [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
    ]
    
    if data == "admin:close":
        await query.message.delete()
    
    elif data == "admin:menu":
        active_tasks = get_active_tasks()
        await query.message.edit_text(
            "🔧 **Admin Control Panel**\n\n"
            f"📋 Active Tasks: **{len(active_tasks)}**\n"
            f"⏱️ Uptime: {get_readable_time(int(time.time() - _bot_start_time))}\n\n"
            "Select an option below:",
            parse_mode='Markdown',
            reply_markup=_admin_menu_keyboard()
        )
    
    elif data == "admin:status":
        status = _get_system_status_detailed()
        await query.message.edit_text(
            status, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(refresh_back)
        )
    
    elif data == "admin:storage":
        storage_info = await _get_storage_info()
        buttons = [
            [InlineKeyboardButton("🧹 Clean Downloads", callback_data="admin:clean")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin:storage")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
        ]
        await query.message.edit_text(
            storage_info, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif data == "admin:clean":
        # Clean old files from downloads
        try:
            cleaned = 0
            cleaned_size = 0
            for f in DOWNLOADS_PATH.glob("*"):
                if f.is_file():
                    age = time.time() - f.stat().st_mtime
                    if age > 3600:  # Older than 1 hour
                        size = f.stat().st_size
                        f.unlink()
                        cleaned += 1
                        cleaned_size += size
            
            await query.answer(
                f"🧹 Cleaned {cleaned} files ({humanbytes(cleaned_size)})",
                show_alert=True
            )
        except Exception as e:
            await query.answer(f"Error: {str(e)[:50]}", show_alert=True)
        
        # Refresh storage view
        storage_info = await _get_storage_info()
        buttons = [
            [InlineKeyboardButton("🧹 Clean Downloads", callback_data="admin:clean")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin:storage")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin:menu")]
        ]
        await query.message.edit_text(
            storage_info, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif data == "admin:tasks":
        tasks = get_active_tasks()
        
        if not tasks:
            text = "📋 **Active Tasks**\n\n_No active tasks._"
            await query.message.edit_text(
                text, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(refresh_back)
            )
        else:
            text = f"📋 **Active Tasks** ({len(tasks)})\n\n"
            buttons = []
            
            for (uid, tid), info in tasks.items():
                progress = info.get('progress', 0)
                bar_filled = int(progress / 10)
                bar = '█' * bar_filled + '░' * (10 - bar_filled)
                
                text += (
                    f"**User:** `{uid}`\n"
                    f"**File:** `{info.get('file_name', 'Unknown')[:25]}...`\n"
                    f"**Progress:** [{bar}] {progress:.1f}%\n"
                    f"**Speed:** {info.get('speed', 'N/A')} | **ETA:** {info.get('eta', 'N/A')}\n"
                    f"───────────────\n"
                )
                buttons.append([InlineKeyboardButton(
                    f"❌ Cancel Task {tid}", 
                    callback_data=f"admin:cancel:{uid}:{tid}"
                )])
            
            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin:tasks")])
            buttons.append([InlineKeyboardButton("◀️ Back", callback_data="admin:menu")])
            
            await query.message.edit_text(
                text[:4096], parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    
    elif data == "admin:stats":
        try:
            stats = await get_leech_stats()
            
            text = (
                "📊 **Leech Statistics**\n\n"
                f"**All Time:**\n"
                f"├ Total Tasks: {stats['total_tasks']}\n"
                f"├ Completed: {stats['completed']} ✅\n"
                f"├ Failed: {stats['failed']} ❌\n"
                f"├ Cancelled: {stats['cancelled']} 🚫\n"
                f"└ Total Data: {humanbytes(stats['total_bytes'])}\n\n"
                f"**Today:**\n"
                f"├ Tasks: {stats['today_tasks']}\n"
                f"└ Data: {humanbytes(stats['today_bytes'])}"
            )
            
            await query.message.edit_text(
                text, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(refresh_back)
            )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            await query.message.edit_text(
                "❌ Error fetching statistics. Database may not be initialized.",
                reply_markup=InlineKeyboardMarkup(back_button)
            )
    
    elif data == "admin:history":
        try:
            stats = await get_leech_stats()
            recent = stats.get('recent', [])
            
            if not recent:
                text = "📜 **Task History**\n\n_No tasks recorded yet._"
            else:
                text = "📜 **Recent Tasks** (Last 10)\n\n"
                for task in recent[:10]:
                    status_icon = {
                        'completed': '✅',
                        'failed': '❌', 
                        'cancelled': '🚫',
                        'downloading': '⬇️',
                        'uploading': '⬆️'
                    }.get(task['status'], '⏳')
                    
                    user_name = task.get('username') or task.get('first_name') or str(task['user_id'])
                    file_name = (task.get('file_name') or 'Unknown')[:20]
                    target = task.get('upload_target', 'N/A')
                    
                    text += (
                        f"{status_icon} `{file_name}...`\n"
                        f"   └ {user_name} → {target}\n"
                    )
            
            await query.message.edit_text(
                text[:4096], parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(refresh_back)
            )
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            await query.message.edit_text(
                "❌ Error fetching history.",
                reply_markup=InlineKeyboardMarkup(back_button)
            )
    
    elif data == "admin:users":
        try:
            users = await get_all_leech_users()
            
            if not users:
                text = "👥 **Leech Users**\n\n_No users with leech settings._"
            else:
                text = f"👥 **Leech Users** ({len(users)})\n\n"
                for u in users[:15]:
                    nc_icon = "✅" if u['nc_configured'] else "⚠️"
                    delete_icon = "🗑️" if u['nc_auto_delete'] else "💾"
                    text += (
                        f"{nc_icon} `{u['user_id']}` - {u['username'][:15]}\n"
                        f"   └ NC: {nc_icon} | {delete_icon} {u['nc_delete_timer']}m\n"
                    )
                
                if len(users) > 15:
                    text += f"\n_... and {len(users) - 15} more_"
            
            await query.message.edit_text(
                text[:4096], parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(refresh_back)
            )
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            await query.message.edit_text(
                "❌ Error fetching users.",
                reply_markup=InlineKeyboardMarkup(back_button)
            )
    
    elif data.startswith("admin:cancel:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        
        target_uid = int(parts[2])
        target_tid = int(parts[3])
        
        task = get_task(target_uid, target_tid)
        if task:
            task.cancel()
            await query.answer("✅ Task cancellation requested.", show_alert=True)
        else:
            await query.answer("Task not found or already completed.", show_alert=True)
        
        # Refresh task list
        # Trigger tasks view refresh
        query.data = "admin:tasks"
        await admin_callback(update, context)
