"""
Leech command handlers - Download files from URLs to Telegram or Nextcloud.
"""

import os
import re
import time
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, Tuple
from urllib.parse import quote, urlparse
from contextlib import suppress

import httpx
import requests
import psutil
import aiofiles
from aiofiles.os import remove as aioremove
from aiofiles.os import path as aiopath
from aiofiles.os import stat as aiostat

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import DOWNLOADS_PATH, MAX_FILE_SIZE_MB
from tg_bot.uploader import upload_document
from services.leech_data import (
    get_nc_settings, is_nc_configured, get_all_leech_users,
    record_leech_start, update_leech_status,
    DEFAULT_NC_DELETE_TIMER
)

logger = logging.getLogger(__name__)

# Task management
_user_tasks: Dict[int, list] = {}
_active_tasks: Dict[Tuple[int, int], asyncio.Task] = {}
_task_statuses: Dict[Tuple[int, int], Dict[str, Any]] = {}
_user_task_lock = asyncio.Lock()

# Constants
USER_TASK_LIMIT = 10
UPDATE_INTERVAL = 1
_bot_start_time = time.time()


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
        result += f"{days}d"
    if hours > 0:
        result += f"{hours}h"
    if minutes > 0:
        result += f"{minutes}m"
    if seconds > 0 or not result:
        result += f"{seconds}s"
    return result if result else "0s"


def get_system_status() -> str:
    """Get current system status."""
    try:
        cpu = psutil.cpu_percent()
        disk_info = psutil.disk_usage(str(DOWNLOADS_PATH))
        free = humanbytes(disk_info.free)
        ram = psutil.virtual_memory().percent
        uptime = get_readable_time(int(time.time() - _bot_start_time))
        num_tasks = len(_active_tasks)
        return (
            f"💻 CPU: {cpu}% | 🧠 FREE: {free}\n"
            f"📉 RAM: {ram}% | ⏱️ UPTIME: {uptime}\n"
            f"📋 Active Tasks: {num_tasks}"
        )
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return "CPU: - | FREE: - | RAM: - | UPTIME: -"


def get_cancel_button(user_id: int, task_id: int) -> InlineKeyboardMarkup:
    """Create cancel button for a task."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"leech:cancel:{user_id}:{task_id}")]
    ])


async def _edit_status(message, text: str, reply_markup=None) -> None:
    """Safely edit a status message."""
    if not message:
        return
    try:
        text = text[:4096]
        await message.edit_text(
            text, 
            disable_web_page_preview=True, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.debug(f"Error editing status: {e}")


# ============ WebDAV / Nextcloud Functions ============

def _sync_upload_webdav(webdav_url: str, local_file_path: str, 
                         username: str, password: str, save_name: str) -> requests.Response:
    """Upload file to Nextcloud via WebDAV (sync, runs in thread)."""
    headers = {'Content-Type': 'application/octet-stream'}
    full_url = f"{webdav_url}temp/{save_name}"
    try:
        with open(local_file_path, 'rb') as file:
            response = requests.put(
                full_url, data=file, headers=headers,
                auth=(username, password), timeout=600
            )
        logger.info(f"WebDAV Upload: Status {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"WebDAV Upload Exception: {e}")
        mock_response = requests.Response()
        mock_response.status_code = 500
        mock_response._content = str(e).encode()
        return mock_response


def _sync_get_share_link(username: str, password: str, 
                          save_name: str, webdav_url: str) -> requests.Response:
    """Get share link from Nextcloud OCS API (sync, runs in thread)."""
    headers = {"OCS-APIRequest": "true"}
    payload = {"path": f"/temp/{save_name}", "shareType": 3, "permissions": 1}
    parsed_url = urlparse(webdav_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    ocs_url = f"{base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
    try:
        response = requests.post(
            ocs_url, auth=(username, password),
            headers=headers, data=payload, timeout=60
        )
        return response
    except Exception as e:
        logger.error(f"Share Link Exception: {e}")
        mock_response = requests.Response()
        mock_response.status_code = 500
        mock_response._content = str(e).encode()
        return mock_response


def _sync_delete_webdav(webdav_url: str, username: str, 
                         password: str, save_name: str) -> bool:
    """Delete file from Nextcloud via WebDAV (sync, runs in thread)."""
    full_url = f"{webdav_url.rstrip('/')}/remote.php/dav/files/{username}/temp/{quote(save_name)}"
    try:
        response = requests.delete(full_url, auth=(username, password), timeout=60)
        return response.status_code in (200, 204, 404)
    except requests.exceptions.RequestException as e:
        logger.error(f"WebDAV Delete Exception: {e}")
        return False


async def schedule_nextcloud_deletion(webdav_url: str, username: str, 
                                       password: str, save_name: str, 
                                       delay_minutes: int, task_id: int) -> None:
    """Schedule deletion of a Nextcloud file after delay."""
    await asyncio.sleep(delay_minutes * 60)
    logger.info(f"Task {task_id} - Auto-deleting '{save_name}' after {delay_minutes}min")
    deleted = await asyncio.to_thread(
        _sync_delete_webdav, webdav_url, username, password, save_name
    )
    if deleted:
        logger.info(f"Task {task_id} - Deleted '{save_name}' from Nextcloud")
    else:
        logger.error(f"Task {task_id} - Failed to delete '{save_name}'")


async def _upload_to_nextcloud(
    user_id: int, 
    download_path: str, 
    file_name: str,
    status_message,
    task_id: int
) -> str:
    """Upload file to Nextcloud and return share link."""
    settings = await get_nc_settings(user_id)
    nc_user = settings['user_name']
    nc_pass = settings['password']
    webdav_url = settings['link']
    auto_delete = settings.get('nc_auto_delete', True)
    delete_timer = settings.get('nc_delete_timer', DEFAULT_NC_DELETE_TIMER)
    
    reply_markup = get_cancel_button(user_id, task_id)
    await _edit_status(
        status_message,
        f"⬆️ Uploading `{file_name}` to Nextcloud...\n\n{get_system_status()}",
        reply_markup
    )
    
    # Upload to WebDAV
    response = await asyncio.to_thread(
        _sync_upload_webdav, webdav_url, download_path, nc_user, nc_pass, file_name
    )
    
    if response.status_code not in (200, 201, 204):
        raise Exception(f"Nextcloud upload failed: {response.status_code}")
    
    await _edit_status(status_message, "✅ Upload successful! Generating share link...")
    
    # Get share link
    share_response = await asyncio.to_thread(
        _sync_get_share_link, nc_user, nc_pass, file_name, webdav_url
    )
    
    final_message = f"🎉 **Upload Successful!**\n\nFile: `{file_name}`\n\n"
    
    if share_response.status_code == 200:
        try:
            root = ET.fromstring(share_response.content)
            share_url_element = root.find(".//url")
            if share_url_element is not None and share_url_element.text:
                public_link = f"{share_url_element.text}/download"
                file_stat = await aiostat(download_path)
                file_size = humanbytes(file_stat.st_size)
                final_message += f"🔗 [Direct download]({public_link}) ({file_size})"
            else:
                final_message += "⚠️ Could not find URL in share response."
        except ET.ParseError as e:
            final_message += f"⚠️ Failed to parse share link: {e}"
    else:
        final_message += f"❌ Failed to get share link (Status: {share_response.status_code})"
    
    # Auto-delete info
    if auto_delete and delete_timer > 0:
        final_message += f"\n\n🗑️ Auto-delete in {delete_timer} min"
        asyncio.create_task(schedule_nextcloud_deletion(
            webdav_url, nc_user, nc_pass, file_name, delete_timer, task_id
        ))
    
    await _edit_status(status_message, final_message, reply_markup=None)
    return final_message


# ============ Main Leech Task ============

async def _run_leech_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    upload_target: str  # 'telegram' or 'nextcloud'
) -> None:
    """Core leech task - download URL and upload to target."""
    user_id = update.effective_user.id
    task_id = update.message.message_id
    status_message = None
    download_path = None
    file_name = f"file_{task_id}"
    
    try:
        reply_markup = get_cancel_button(user_id, task_id)
        status_message = await update.message.reply_text(
            f"⏳ Processing: `{url[:60]}...`\n\n{get_system_status()}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        _task_statuses[(user_id, task_id)] = {
            "status": "Starting",
            "file_name": "Unknown",
            "progress": 0,
            "speed": "0B/s",
            "eta": "-",
        }
        
        start_time = time.time()
        
        # Download file
        async with httpx.AsyncClient(follow_redirects=True, timeout=90.0) as http_client:
            async with http_client.stream("GET", url) as response:
                response.raise_for_status()
                
                # Extract filename
                if "content-disposition" in response.headers:
                    cd = response.headers["content-disposition"]
                    fname_match = re.search(
                        r'filename\*?=(?:UTF-8\'\')?([\'"]?)(.*?)\1(?:;|$)',
                        cd, re.IGNORECASE
                    )
                    if fname_match:
                        file_name = requests.utils.unquote(fname_match.group(2))
                
                if file_name == f"file_{task_id}":
                    try:
                        parsed_path = urlparse(str(response.url)).path
                        fname_from_path = os.path.basename(parsed_path)
                        if fname_from_path and '.' in fname_from_path:
                            file_name = requests.utils.unquote(fname_from_path)
                    except Exception:
                        pass
                
                # Sanitize filename
                file_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', file_name).strip('._')
                if not file_name:
                    file_name = f"dl_{task_id}_{int(time.time())}"
                
                # Truncate if too long
                if len(file_name.encode('utf-8')) > 240:
                    name_part, ext_part = os.path.splitext(file_name)
                    max_len = 240 - len(ext_part.encode('utf-8'))
                    while len(name_part.encode('utf-8')) > max_len:
                        name_part = name_part[:-1]
                    file_name = name_part + ext_part
                
                download_path = str(DOWNLOADS_PATH / file_name)
                total_size = int(response.headers.get('content-length', 0))
                size_info = f" ({humanbytes(total_size)})" if total_size else ""
                
                await _edit_status(
                    status_message,
                    f"⏳ Downloading `{file_name}`{size_info}\n\n{get_system_status()}",
                    reply_markup
                )
                
                # Stream download
                downloaded = 0
                last_update = 0
                async with aiofiles.open(download_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024*1024):
                        if not chunk:
                            break
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress
                        now = time.time()
                        if now - last_update >= UPDATE_INTERVAL:
                            last_update = now
                            if total_size > 0:
                                pct = downloaded * 100 / total_size
                                elapsed = now - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = get_readable_time((total_size - downloaded) / speed) if speed > 0 else "-"
                                
                                filled = int(pct / 6.25)
                                bar = '▰' * filled + '▱' * (16 - filled)
                                
                                progress_text = (
                                    f"**Downloading** {pct:.1f}%\n"
                                    f"{bar}\n"
                                    f"📁 {humanbytes(downloaded)} / {humanbytes(total_size)}\n"
                                    f"⚡ {humanbytes(speed)}/s | ⏱ ETA: {eta}\n\n"
                                    f"📝 File: `{file_name}`"
                                )
                                await _edit_status(
                                    status_message,
                                    f"{progress_text}\n\n{get_system_status()}",
                                    reply_markup
                                )
                                
                                _task_statuses[(user_id, task_id)].update({
                                    "file_name": file_name,
                                    "progress": pct,
                                    "speed": humanbytes(speed),
                                    "eta": eta,
                                })
        
        download_duration = time.time() - start_time
        await _edit_status(
            status_message,
            f"✅ Download complete in {get_readable_time(download_duration)}. Preparing upload...",
            reply_markup
        )
        
        # Check file size
        file_stat = await aiostat(download_path)
        file_size = file_stat.st_size
        
        if file_size == 0:
            raise Exception("Downloaded file is empty.")
        
        if upload_target == 'telegram' and file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise Exception(f"File size ({humanbytes(file_size)}) exceeds Telegram limit ({MAX_FILE_SIZE_MB} MB).")
        
        # Upload
        if upload_target == 'telegram':
            file_stat = await aiostat(download_path)
            total_size = file_stat.st_size
            
            async def tg_progress(current: int, total: int):
                """Update status message with upload progress."""
                pct = (current / total) * 100 if total > 0 else 0
                filled = int(pct / 6.25)
                bar = '▰' * filled + '▱' * (16 - filled)
                progress_text = (
                    f"**Uploading to Telegram** {pct:.1f}%\n"
                    f"{bar}\n"
                    f"📁 {humanbytes(current)} / {humanbytes(total)}\n\n"
                    f"📝 File: `{file_name}`"
                )
                await _edit_status(status_message, progress_text, reply_markup)
            
            await _edit_status(
                status_message,
                f"⬆️ Uploading `{file_name}` ({humanbytes(total_size)}) to Telegram...",
                reply_markup
            )
            
            message_id = await upload_document(
                chat_id=user_id,
                file_path=download_path,
                caption=f"`{file_name}`",
                file_name=file_name,
                reply_to_message_id=task_id,
                progress_callback=tg_progress,
            )
            
            if message_id:
                await _edit_status(status_message, "✅ Upload complete!", reply_markup=None)
                await asyncio.sleep(5)
                with suppress(Exception):
                    await status_message.delete()
            else:
                raise Exception("Telegram upload failed")
        
        elif upload_target == 'nextcloud':
            await _upload_to_nextcloud(
                user_id, download_path, file_name, status_message, task_id
            )
    
    except asyncio.CancelledError:
        await _edit_status(status_message, "❌ Task cancelled.", reply_markup=None)
        await asyncio.sleep(5)
        with suppress(Exception):
            await status_message.delete()
        raise
    
    except Exception as e:
        error_msg = f"❌ Task Failed!\n\n**Error:** {str(e)[:500]}"
        logger.error(f"Leech task {task_id} failed: {e}")
        if status_message:
            await _edit_status(status_message, error_msg, reply_markup=None)
            await asyncio.sleep(15)
            with suppress(Exception):
                await status_message.delete()
        else:
            await update.message.reply_text(error_msg, parse_mode='Markdown')
    
    finally:
        # Cleanup
        async with _user_task_lock:
            if user_id in _user_tasks and task_id in _user_tasks[user_id]:
                _user_tasks[user_id].remove(task_id)
                if not _user_tasks[user_id]:
                    del _user_tasks[user_id]
            if (user_id, task_id) in _active_tasks:
                del _active_tasks[(user_id, task_id)]
            if (user_id, task_id) in _task_statuses:
                del _task_statuses[(user_id, task_id)]
        
        if download_path and await aiopath.exists(download_path):
            with suppress(OSError):
                await aioremove(download_path)
                logger.info(f"Cleaned up: {download_path}")


# ============ Command Handlers ============

async def leech_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /l command - download URL to Telegram."""
    if not context.args:
        await update.message.reply_text(
            "📥 **Leech to Telegram**\n\n"
            "Download a file from a direct URL and upload to Telegram.\n\n"
            "Usage: `/l <url>`\n"
            "Example: `/l https://example.com/file.zip`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0].strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Invalid URL. Must start with `http://` or `https://`.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    task_id = update.message.message_id
    
    async with _user_task_lock:
        current_tasks = len(_user_tasks.get(user_id, []))
        if current_tasks >= USER_TASK_LIMIT:
            await update.message.reply_text(
                f"⚠️ Task limit ({USER_TASK_LIMIT}) reached. Wait for tasks to complete."
            )
            return
        
        _user_tasks.setdefault(user_id, []).append(task_id)
        task = asyncio.create_task(_run_leech_task(update, context, url, 'telegram'))
        _active_tasks[(user_id, task_id)] = task


async def leech_nextcloud_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ld command - download URL to Nextcloud."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "☁️ **Leech to Nextcloud**\n\n"
            "Download a file from a direct URL and upload to your Nextcloud.\n\n"
            "Usage: `/ld <url>`\n"
            "Example: `/ld https://example.com/file.zip`\n\n"
            "⚙️ Configure with `/setnc` first!",
            parse_mode='Markdown'
        )
        return
    
    # Check if NC is configured
    if not await is_nc_configured(user_id):
        await update.message.reply_text(
            "❌ Nextcloud not configured!\n\n"
            "Use `/setnc` to set up your Nextcloud credentials first.",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0].strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Invalid URL. Must start with `http://` or `https://`.", parse_mode='Markdown')
        return
    
    task_id = update.message.message_id
    
    async with _user_task_lock:
        current_tasks = len(_user_tasks.get(user_id, []))
        if current_tasks >= USER_TASK_LIMIT:
            await update.message.reply_text(
                f"⚠️ Task limit ({USER_TASK_LIMIT}) reached. Wait for tasks to complete."
            )
            return
        
        _user_tasks.setdefault(user_id, []).append(task_id)
        task = asyncio.create_task(_run_leech_task(update, context, url, 'nextcloud'))
        _active_tasks[(user_id, task_id)] = task


async def leech_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle leech-related callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("leech:cancel:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        
        target_user_id = int(parts[2])
        task_id = int(parts[3])
        
        # Only task owner can cancel
        if query.from_user.id != target_user_id:
            await query.answer("This is not your task.", show_alert=True)
            return
        
        task = _active_tasks.get((target_user_id, task_id))
        if task:
            task.cancel()
            await query.answer("Task cancellation requested.")
        else:
            await query.answer("Task not found or completed.", show_alert=True)


# Export task info for admin panel
def get_active_tasks() -> Dict[Tuple[int, int], Dict[str, Any]]:
    """Get all active task statuses."""
    return _task_statuses.copy()


def get_task(user_id: int, task_id: int) -> Optional[asyncio.Task]:
    """Get a specific task."""
    return _active_tasks.get((user_id, task_id))
