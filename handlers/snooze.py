"""
Snooze handler for notification reminder management.
"""

import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from database import add_snooze, dismiss_snooze, get_channel_video
from tg_bot.keyboards import snooze_keyboard

logger = logging.getLogger(__name__)

# Snooze duration mapping
SNOOZE_DURATIONS = {
    '1h': timedelta(hours=1),
    '12h': timedelta(hours=12),
    '1d': timedelta(days=1),
    '3d': timedelta(days=3),
    '1w': timedelta(weeks=1),
    '1m': timedelta(days=30),
}


async def snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle snooze-related callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split(':')
    action = parts[1]
    
    user_id = update.effective_user.id
    
    if action == 'menu':
        # Show snooze duration menu
        video_id = parts[2]
        channel_id = parts[3] if len(parts) > 3 else ''
        
        await query.edit_message_reply_markup(
            reply_markup=snooze_keyboard(video_id, channel_id)
        )
        
    elif action in SNOOZE_DURATIONS:
        # Snooze for the specified duration
        video_id = parts[2]
        channel_id = parts[3] if len(parts) > 3 else ''
        
        duration = SNOOZE_DURATIONS[action]
        remind_at = datetime.now() + duration
        
        # Get video title from channel_videos table
        video_record = await get_channel_video(video_id)
        video_title = video_record['title'] if video_record else 'Video'
        
        # Save snooze
        await add_snooze(
            user_id=user_id,
            video_id=video_id,
            channel_id=channel_id,
            video_title=video_title,
            remind_at=remind_at
        )
        
        # Format duration for display
        duration_text = {
            '1h': '1 hour',
            '12h': '12 hours',
            '1d': '1 day',
            '3d': '3 days',
            '1w': '1 week',
            '1m': '1 month',
        }.get(action, action)
        
        await query.edit_message_text(
            f"⏰ **Snoozed for {duration_text}**\n\n"
            f"I'll remind you about this video later!",
            parse_mode='Markdown'
        )


async def notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle notification-related callbacks (dismiss, etc.)."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split(':')
    action = parts[1]
    
    user_id = update.effective_user.id
    
    if action == 'dismiss':
        video_id = parts[2]
        
        # Dismiss any active snooze for this video
        await dismiss_snooze(user_id, video_id)
        
        await query.edit_message_text(
            "✅ Notification dismissed.",
            parse_mode='Markdown'
        )
