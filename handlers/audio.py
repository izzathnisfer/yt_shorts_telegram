"""
Audio command handler - Download audio only.
"""

from telegram import Update
from telegram.ext import ContextTypes

from youtube.utils import extract_video_id, is_youtube_url
from youtube.info import get_video_info
from youtube.downloader import download_audio, delete_file
from tg_bot.uploader import upload_audio


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /audio command."""
    if not context.args:
        await update.message.reply_text(
            "🎵 **Download Audio**\n\n"
            "Usage: `/audio <url>`\n\n"
            "Example:\n"
            "`/audio https://youtu.be/abc123`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    if not is_youtube_url(url):
        await update.message.reply_text("❌ Please provide a valid YouTube URL.")
        return
    
    user_id = update.effective_user.id
    
    # Get video info
    loading = await update.message.reply_text("⏳ Getting video info...")
    
    info = await get_video_info(url)
    if not info:
        await loading.edit_text("❌ Could not get video info. Check the URL.")
        return
    
    if info.get('is_live'):
        await loading.edit_text("🔴 Cannot extract audio from live streams.")
        return
    
    # Download audio
    await loading.edit_text(f"🎵 Extracting audio: {info['title'][:40]}...")
    
    file_path = await download_audio(url)
    
    if not file_path:
        await loading.edit_text("❌ Audio extraction failed. Please try again.")
        return
    
    # Upload
    await loading.edit_text("📤 Uploading audio...")
    
    caption = f"🎵 **{info['title']}**\n📺 {info['channel_name']}"
    
    message_id = await upload_audio(
        chat_id=user_id,
        file_path=file_path,
        caption=caption,
        title=info['title'],
        performer=info['channel_name'],
        duration=info['duration'],
    )
    
    # Cleanup
    delete_file(file_path)
    
    if message_id:
        await loading.edit_text("✅ Audio sent!")
    else:
        await loading.edit_text("❌ Upload failed. Please try again.")
