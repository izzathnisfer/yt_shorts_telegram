"""
Global callback handler for common actions.
Handles downloads, favorites, skips, and other shared callbacks.
"""

from telegram import Update
from telegram.ext import ContextTypes
import logging

from database import (
    add_favorite, remove_favorite, add_to_queue, remove_from_queue,
    check_duplicate, add_to_history, record_watch, get_user_settings,
    mark_video_seen
)
from youtube.info import get_video_info
from youtube.downloader import download_video, download_audio, delete_file
from youtube.utils import build_video_url
from tg_bot.uploader import upload_video, upload_audio
from tg_bot.keyboards import duplicate_warning_keyboard

logger = logging.getLogger(__name__)


async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle global callback queries."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # Download video
    if data.startswith('dl:video:') or data.startswith('dl:force:'):
        video_id = data.split(':')[2]
        force = data.startswith('dl:force:')
        await handle_video_download(update, context, video_id, force)
    
    # Download audio
    elif data.startswith('dl:audio:'):
        video_id = data.split(':')[2]
        await handle_audio_download(update, context, video_id)
    
    # Add to favorites
    elif data.startswith('fav:add:'):
        video_id = data.split(':')[2]
        await handle_add_favorite(update, context, video_id)
    
    # Add to queue
    elif data.startswith('queue:add:'):
        video_id = data.split(':')[2]
        await handle_add_to_queue(update, context, video_id)
    
    # Skip (just acknowledge)
    elif data.startswith('skip:'):
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("Skipped ⏭️")
    
    # Cancel
    elif data == 'cancel':
        await query.edit_message_text("❌ Cancelled.")
    
    # Quick subscribe from search
    elif data.startswith('sub:quick:'):
        channel_id = data.split(':')[2]
        from handlers.subscribe import quick_subscribe
        await quick_subscribe(update, context, channel_id)


async def handle_video_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_id: str,
    force: bool = False
) -> None:
    """Handle video download request."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check for duplicate
    if not force:
        duplicate = await check_duplicate(user_id, video_id)
        if duplicate:
            from datetime import datetime
            watched_at = duplicate.get('watched_at', '')
            if watched_at:
                try:
                    date = datetime.fromisoformat(watched_at).strftime('%b %d, %Y')
                except:
                    date = 'previously'
            else:
                date = 'previously'
            
            await query.edit_message_text(
                f"⚠️ **Already Downloaded!**\n\n"
                f"You downloaded this video on {date}.\n\n"
                f"🎬 {duplicate.get('title', 'Unknown')}",
                parse_mode='Markdown',
                reply_markup=duplicate_warning_keyboard(video_id)
            )
            return
    
    # Get video info
    url = build_video_url(video_id)
    await query.edit_message_text("⏳ Getting video info...")
    
    info = await get_video_info(url)
    if not info:
        await query.edit_message_text("❌ Could not get video info. Please try again.")
        return
    
    # Get user settings for quality
    settings = await get_user_settings(user_id)
    quality = settings.get('resolution', '720')
    
    await query.edit_message_text(f"📥 Downloading: {info['title'][:50]}...")
    
    # Download video
    file_path = await download_video(url, quality=quality)
    
    if not file_path:
        await query.edit_message_text("❌ Download failed. Please try again.")
        return
    
    await query.edit_message_text(f"📤 Uploading to Telegram...")
    
    # Prepare caption
    caption = f"🎬 **{info['title']}**\n\n"
    caption += f"📺 {info['channel_name']}\n"
    caption += f"⏱️ {info['duration_string']}"
    
    # Upload to Telegram
    message_id = await upload_video(
        chat_id=user_id,
        file_path=file_path,
        caption=caption,
        duration=info['duration'],
        width=info.get('width', 0),
        height=info.get('height', 0),
    )
    
    # Clean up file
    delete_file(file_path)
    
    if message_id:
        # Record in history
        await add_to_history(
            user_id=user_id,
            video_id=video_id,
            title=info['title'],
            channel_id=info['channel_id'],
            channel_name=info['channel_name'],
            duration=info['duration'],
            is_short=info['is_short'],
            source='download'
        )
        
        # Record stats
        await record_watch(
            user_id=user_id,
            channel_id=info['channel_id'],
            channel_name=info['channel_name'],
            duration=info['duration'],
            is_short=info['is_short']
        )
        
        await query.edit_message_text("✅ Video sent!")
    else:
        await query.edit_message_text("❌ Upload failed. Please try again.")


async def handle_audio_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_id: str
) -> None:
    """Handle audio download request."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    url = build_video_url(video_id)
    await query.edit_message_text("⏳ Getting video info...")
    
    info = await get_video_info(url)
    if not info:
        await query.edit_message_text("❌ Could not get video info. Please try again.")
        return
    
    await query.edit_message_text(f"🎵 Extracting audio: {info['title'][:50]}...")
    
    # Download audio
    file_path = await download_audio(url)
    
    if not file_path:
        await query.edit_message_text("❌ Audio extraction failed. Please try again.")
        return
    
    await query.edit_message_text(f"📤 Uploading audio...")
    
    # Upload to Telegram
    caption = f"🎵 **{info['title']}**\n📺 {info['channel_name']}"
    
    message_id = await upload_audio(
        chat_id=user_id,
        file_path=file_path,
        caption=caption,
        title=info['title'],
        performer=info['channel_name'],
        duration=info['duration'],
    )
    
    # Clean up file
    delete_file(file_path)
    
    if message_id:
        await query.edit_message_text("✅ Audio sent!")
    else:
        await query.edit_message_text("❌ Upload failed. Please try again.")


async def handle_add_favorite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_id: str
) -> None:
    """Handle add to favorites request."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Get video info
    url = build_video_url(video_id)
    info = await get_video_info(url)
    
    if not info:
        await query.answer("❌ Could not get video info", show_alert=True)
        return
    
    success = await add_favorite(
        user_id=user_id,
        video_id=video_id,
        video_url=url,
        title=info['title'],
        channel_name=info['channel_name'],
        duration=info['duration'],
        thumbnail_url=info.get('thumbnail')
    )
    
    if success:
        await query.answer("⭐ Added to favorites!")
    else:
        await query.answer("Already in favorites", show_alert=True)


async def handle_add_to_queue(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_id: str
) -> None:
    """Handle add to queue request."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Get video info
    url = build_video_url(video_id)
    info = await get_video_info(url)
    
    if not info:
        await query.answer("❌ Could not get video info", show_alert=True)
        return
    
    success = await add_to_queue(
        user_id=user_id,
        video_id=video_id,
        video_url=url,
        title=info['title'],
        channel_name=info['channel_name'],
        duration=info['duration'],
        thumbnail_url=info.get('thumbnail')
    )
    
    if success:
        await query.answer("📋 Added to queue!")
    else:
        await query.answer("Already in queue", show_alert=True)
