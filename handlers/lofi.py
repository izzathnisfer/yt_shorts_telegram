"""
Lofi command handler - Lofi music for studying.
"""

from telegram import Update
from telegram.ext import ContextTypes

from youtube.search import search_lofi
from youtube.info import get_video_info
from youtube.downloader import download_audio, download_audio_trimmed, delete_file
from youtube.utils import parse_duration_string, format_duration_long
from tg_bot.uploader import upload_audio
from tg_bot.keyboards import lofi_duration_keyboard, back_button
from database import add_to_history, record_watch


async def lofi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lofi command."""
    # Check for duration argument
    if context.args:
        duration_str = context.args[0]
        duration_minutes = parse_duration_string(duration_str)
        
        if duration_minutes:
            duration_minutes = duration_minutes // 60  # Convert seconds to minutes
            await send_lofi(update, context, duration_minutes)
            return
    
    await show_lofi_menu(update, context)


async def show_lofi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show lofi duration selection."""
    message = """
🎧 **Lofi Study Mode**

Get curated lofi music for focused studying.
No distractions, just chill beats!

How long do you need to focus?

Or type: `/lofi 45m` for custom duration
"""
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                message,
                parse_mode='Markdown',
                reply_markup=lofi_duration_keyboard()
            )
        except Exception:
            pass  # Ignore "Message is not modified" errors
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=lofi_duration_keyboard()
        )


async def lofi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle lofi callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('lofi:'):
        duration_str = data.split(':')[1]
        if duration_str.isdigit():
            duration_minutes = int(duration_str)
            await send_lofi(update, context, duration_minutes)


async def send_lofi(update: Update, context: ContextTypes.DEFAULT_TYPE, duration_minutes: int) -> None:
    """Search, download, and send lofi music."""
    user_id = update.effective_user.id
    
    # Register with task manager
    from services.task_manager import get_task_manager, TaskType
    tm = get_task_manager()
    tm_task_id = await tm.register_task(
        user_id=user_id,
        task_type=TaskType.AUDIO_DOWNLOAD,
        file_name=f"lofi_{duration_minutes}m.mp3"
    )
    
    try:
        # Get the message to edit
        if update.callback_query:
            message = update.callback_query.message
            await message.edit_text(
                f"🎧 Finding lofi music for {format_duration_long(duration_minutes * 60)}...",
                parse_mode='Markdown'
            )
        else:
            message = await update.message.reply_text(
                f"🎧 Finding lofi music for {format_duration_long(duration_minutes * 60)}...",
                parse_mode='Markdown'
            )
        
        # Search for lofi tracks
        results = await search_lofi(duration_minutes)
        
        if not results:
            await message.edit_text(
                "❌ Couldn't find suitable lofi music. Please try again.",
                reply_markup=back_button()
            )
            return
        
        # Get recently sent lofi video IDs (within 30 days) to avoid repetition
        from database import get_recent_lofi_ids
        recent_ids = await get_recent_lofi_ids(user_id, days=30)
        
        # Filter out recently sent videos
        fresh_results = [r for r in results if r['id'] not in recent_ids]
        
        # Pick the best match - prefer fresh results, fallback to any if all recently sent
        if fresh_results:
            selected = fresh_results[0]
        else:
            # All results were sent within 30 days, just use the first one
            selected = results[0]
        
        await message.edit_text(
            f"🎵 Found: {selected['title'][:50]}...\n\n"
            f"📥 Downloading audio..."
        )
        
        # Download audio, trim if needed
        video_duration = selected.get('duration', 0)
        target_duration = duration_minutes * 60
        
        if video_duration > target_duration * 1.2:  # More than 20% longer, trim it
            file_path = await download_audio_trimmed(
                selected['url'],
                start_time=0,
                end_time=target_duration
            )
        else:
            file_path = await download_audio(selected['url'])
        
        if not file_path:
            await message.edit_text(
                "❌ Download failed. Please try again.",
                reply_markup=back_button()
            )
            return
        
        await message.edit_text("📤 Uploading lofi music...")
        
        # Prepare caption
        caption = (
            f"🎧 **Lofi Study Music**\n\n"
            f"🎵 {selected['title']}\n"
            f"⏱️ {format_duration_long(min(target_duration, video_duration))}\n\n"
            f"🧘 *Focus and study well!*"
        )
        
        # Upload
        message_id = await upload_audio(
            chat_id=user_id,
            file_path=file_path,
            caption=caption,
            title=f"Lofi Study - {duration_minutes}min",
            performer="Lofi Music",
            duration=min(target_duration, video_duration),
        )
        
        # Cleanup
        delete_file(file_path)
        
        if message_id:
            # Record in history as lofi
            await add_to_history(
                user_id=user_id,
                video_id=selected['id'],
                title=selected['title'],
                channel_id=selected.get('channel_id', 'lofi'),
                channel_name=selected.get('channel_name', 'Lofi Music'),
                duration=min(target_duration, video_duration),
                is_short=False,
                is_lofi=True,
                source='lofi'
            )
            
            await record_watch(
                user_id=user_id,
                channel_id=selected.get('channel_id', 'lofi'),
                channel_name=selected.get('channel_name', 'Lofi Music'),
                duration=min(target_duration, video_duration),
                is_short=False,
                is_lofi=True
            )
            
            await message.edit_text(
                f"✅ Lofi music sent!\n\n"
                f"🎧 Enjoy your {format_duration_long(duration_minutes * 60)} study session!\n\n"
                f"💡 *Tip: Use /focus {duration_minutes}m to pause notifications*",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
        else:
            await message.edit_text(
                "❌ Upload failed. Please try again.",
                reply_markup=back_button()
            )
    finally:
        # Complete task in task manager
        await tm.complete_task(tm_task_id)
