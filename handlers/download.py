"""
Download command handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

from youtube.utils import extract_video_id, parse_time_range, is_youtube_url
from youtube.info import get_video_info
from youtube.downloader import download_video, download_video_trimmed, delete_file
from youtube.utils import format_views
from tg_bot.uploader import upload_video
from database import get_user_settings, add_to_history, record_watch, check_duplicate
from tg_bot.keyboards import duplicate_warning_keyboard


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /download command."""
    if not context.args:
        await update.message.reply_text(
            "📥 **Download Video**\n\n"
            "Usage:\n"
            "• `/download <url>` - Download full video\n"
            "• `/download <url> 1:30-5:00` - Download trimmed\n\n"
            "Example:\n"
            "`/download https://youtu.be/abc123 0:30-2:00`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    time_range = None
    
    # Check for time range
    if len(context.args) > 1:
        time_range = parse_time_range(context.args[1])
        if not time_range:
            await update.message.reply_text(
                "⚠️ Invalid time format. Use `MM:SS-MM:SS`\n\n"
                "Example: `1:30-5:00`",
                parse_mode='Markdown'
            )
            return
    
    if not is_youtube_url(url):
        await update.message.reply_text("❌ Please provide a valid YouTube URL.")
        return
    
    user_id = update.effective_user.id
    video_id = extract_video_id(url)
    
    # Check for duplicate
    duplicate = await check_duplicate(user_id, video_id)
    if duplicate:
        from datetime import datetime
        watched_at = duplicate.get('watched_at', '')
        try:
            date = datetime.fromisoformat(watched_at).strftime('%b %d, %Y')
        except:
            date = 'previously'
        
        await update.message.reply_text(
            f"⚠️ **Already Downloaded!**\n\n"
            f"You downloaded this video on {date}.\n\n"
            f"🎬 {duplicate.get('title', 'Unknown')}",
            parse_mode='Markdown',
            reply_markup=duplicate_warning_keyboard(video_id)
        )
        return
    
    # Get video info
    loading = await update.message.reply_text("⏳ Getting video info...")
    
    info = await get_video_info(url)
    if not info:
        await loading.edit_text("❌ Could not get video info. Check the URL.")
        return
    
    if info.get('is_live'):
        await loading.edit_text("🔴 Cannot download live streams.")
        return
    
    settings = await get_user_settings(user_id)
    quality = settings.get('resolution', '720')
    
    # Download
    if time_range:
        start, end = time_range
        await loading.edit_text(
            f"📥 Downloading trimmed: {info['title'][:40]}...\n"
            f"⏱️ {start//60}:{start%60:02d} - {end//60}:{end%60:02d}"
        )
        file_path = await download_video_trimmed(url, start, end, quality=quality)
    else:
        await loading.edit_text(f"📥 Downloading: {info['title'][:40]}...")
        file_path = await download_video(url, quality=quality)
    
    if not file_path:
        await loading.edit_text("❌ Download failed. Please try again.")
        return
    
    # Upload
    await loading.edit_text("📤 Uploading to Telegram...")
    
    caption = f"🎬 **{info['title']}**\n\n"
    caption += f"📺 {info['channel_name']}\n"
    caption += f"⏱️ {info['duration_string']}"
    
    message_id = await upload_video(
        chat_id=user_id,
        file_path=file_path,
        caption=caption,
        duration=info['duration'],
        width=info.get('width', 0),
        height=info.get('height', 0),
    )
    
    # Cleanup
    delete_file(file_path)
    
    if message_id:
        # Record history and stats
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
        
        await record_watch(
            user_id=user_id,
            channel_id=info['channel_id'],
            channel_name=info['channel_name'],
            duration=info['duration'],
            is_short=info['is_short']
        )
        
        await loading.edit_text("✅ Video sent!")
    else:
        await loading.edit_text("❌ Upload failed. Please try again.")
