"""
Sync command handler - Bulk download queued videos.
"""

from telegram import Update
from telegram.ext import ContextTypes
import asyncio

from database import get_queue, remove_from_queue, mark_queue_downloaded, add_to_history, record_watch, get_user_settings
from youtube.info import get_video_info
from youtube.downloader import download_video, delete_file
from youtube.utils import format_duration, build_video_url
from tg_bot.uploader import upload_video
from tg_bot.keyboards import back_button


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sync command."""
    await start_sync(update, context)


async def start_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start syncing (bulk download) queue."""
    user_id = update.effective_user.id
    queue_items = await get_queue(user_id)
    
    # Filter out already downloaded
    pending = [item for item in queue_items if not item.get('is_downloaded')]
    
    if not pending:
        message = "📥 **Sync Queue**\n\nNo pending videos to download."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, parse_mode='Markdown', reply_markup=back_button()
            )
        else:
            await update.message.reply_text(
                message, parse_mode='Markdown', reply_markup=back_button()
            )
        return
    
    total = len(pending)
    total_duration = sum(item.get('duration', 0) for item in pending)
    
    message = (
        f"📥 **Sync Queue**\n\n"
        f"📊 {total} videos to download\n"
        f"⏱️ Total: {format_duration(total_duration)}\n\n"
        f"Starting download..."
    )
    
    if update.callback_query:
        status_msg = await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    else:
        status_msg = await update.message.reply_text(message, parse_mode='Markdown')
    
    settings = await get_user_settings(user_id)
    quality = settings.get('resolution', '720')
    
    completed = 0
    failed = 0
    
    for i, item in enumerate(pending, 1):
        # Update status
        await status_msg.edit_text(
            f"📥 **Syncing ({i}/{total})**\n\n"
            f"🎬 {item['title'][:40]}...\n\n"
            f"✅ Completed: {completed}\n"
            f"❌ Failed: {failed}",
            parse_mode='Markdown'
        )
        
        # Register with task manager
        from services.task_manager import get_task_manager, TaskType
        tm = get_task_manager()
        tm_task_id = await tm.register_task(
            user_id=user_id,
            task_type=TaskType.VIDEO_DOWNLOAD,
            file_name=item['title'][:50]
        )
        
        try:
            # Download
            url = item.get('video_url') or build_video_url(item['video_id'])
            file_path = await download_video(url, quality=quality)
            
            if not file_path:
                failed += 1
                continue
            
            # Update task with file path
            await tm.update_task(tm_task_id, file_path=file_path)
            
            # Get fresh info for upload
            info = await get_video_info(url)
            caption = f"🎬 **{item['title']}**\n📺 {item['channel_name']}"
            
            # Upload
            message_id = await upload_video(
                chat_id=user_id,
                file_path=file_path,
                caption=caption,
                duration=item.get('duration', 0),
            )
            
            # Cleanup
            delete_file(file_path)
            
            if message_id:
                completed += 1
                await mark_queue_downloaded(user_id, item['video_id'])
                
                # Record stats
                if info:
                    await add_to_history(
                        user_id=user_id,
                        video_id=item['video_id'],
                        title=item['title'],
                        channel_id=info.get('channel_id', ''),
                        channel_name=item['channel_name'],
                        duration=item['duration'],
                        is_short=info.get('is_short', False),
                        source='sync'
                    )
                    
                    await record_watch(
                        user_id=user_id,
                        channel_id=info.get('channel_id', ''),
                        channel_name=item['channel_name'],
                        duration=item['duration'],
                        is_short=info.get('is_short', False)
                    )
            else:
                failed += 1
        
        except Exception as e:
            failed += 1
        
        finally:
            # Complete task in task manager
            await tm.complete_task(tm_task_id)
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(1)
    
    # Final status
    await status_msg.edit_text(
        f"✅ **Sync Complete!**\n\n"
        f"📊 Downloaded: {completed}/{total}\n"
        f"❌ Failed: {failed}\n\n"
        f"All videos sent above! 👆",
        parse_mode='Markdown',
        reply_markup=back_button()
    )
