"""
Direct YouTube URL handler - handles URLs sent as messages.
"""

from telegram import Update
from telegram.ext import ContextTypes
import logging

from youtube.utils import extract_video_id, is_youtube_url
from youtube.info import get_video_info
from tg_bot.keyboards import thumbnail_preview_keyboard
from youtube.utils import format_views

logger = logging.getLogger(__name__)


async def youtube_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle YouTube URLs sent directly in chat."""
    message = update.message
    text = message.text
    
    # Check if it's a YouTube URL
    if not is_youtube_url(text):
        return
    
    # Extract video ID
    video_id = extract_video_id(text)
    if not video_id:
        await message.reply_text(
            "🤔 I found a YouTube link but couldn't identify the video. "
            "Try sending the full URL."
        )
        return
    
    # Show loading
    loading_msg = await message.reply_text("⏳ Loading video info...")
    
    # Get video info
    info = await get_video_info(text)
    
    if not info:
        await loading_msg.edit_text(
            "❌ Couldn't get video info. The video might be private or unavailable."
        )
        return
    
    # Check if it's a live stream
    if info.get('is_live'):
        await loading_msg.edit_text(
            "🔴 This is a live stream and cannot be downloaded.\n"
            "Wait for the stream to end and try again."
        )
        return
    
    # Format the preview message
    short_icon = "🎬 Short" if info['is_short'] else "📺 Video"
    
    preview_text = f"""
{short_icon} **{info['title']}**

📺 {info['channel_name']}
👁️ {format_views(info['view_count'])} views
⏱️ {info['duration_string']}

What would you like to do?
"""
    
    # Show preview with action buttons
    await loading_msg.edit_text(
        preview_text,
        parse_mode='Markdown',
        reply_markup=thumbnail_preview_keyboard(video_id)
    )
