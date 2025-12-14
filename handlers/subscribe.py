"""
Subscribe command handler - Channel subscription with conversation flow.
"""

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import logging

from database import add_subscription, get_subscription, get_subscriptions
from youtube.search import search_channels
from youtube.info import get_channel_info, get_channel_videos
from tg_bot.keyboards import back_button, confirm_cancel_keyboard

logger = logging.getLogger(__name__)

# Conversation states
WAITING_QUERY, SELECTING_CHANNEL, CONFIRMING = range(3)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /subscribe command."""
    await update.message.reply_text(
        "📺 **Subscribe to a Channel**\n\n"
        "Send me a channel name or YouTube URL:\n\n"
        "Examples:\n"
        "• `MKBHD`\n"
        "• `https://youtube.com/@MKBHD`\n\n"
        "Send /cancel to cancel.",
        parse_mode='Markdown'
    )
    return WAITING_QUERY


async def receive_channel_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and search for channel."""
    query = update.message.text.strip()
    user_id = update.effective_user.id
    
    await update.message.reply_text("🔍 Searching for channels...")
    
    # Check if it's a direct URL
    if 'youtube.com' in query or 'youtu.be' in query:
        channel_info = await get_channel_info(query)
        if channel_info:
            context.user_data['selected_channel'] = channel_info
            return await show_channel_preview(update, context, channel_info)
    
    # Search for channels
    channels = await search_channels(query, limit=5)
    
    if not channels:
        await update.message.reply_text(
            "❌ No channels found. Try a different search term or URL.\n\n"
            "Send /cancel to cancel.",
            parse_mode='Markdown'
        )
        return WAITING_QUERY
    
    # Store search results
    context.user_data['channel_results'] = channels
    
    # Build channel selection keyboard
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = []
    for i, channel in enumerate(channels):
        keyboard.append([
            InlineKeyboardButton(
                f"📺 {channel['name']}",
                callback_data=f"sub:select:{i}"
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="sub:cancel")])
    
    await update.message.reply_text(
        "📺 **Select a channel to subscribe:**",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SELECTING_CHANNEL


async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle channel selection from search results."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'sub:cancel':
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    
    # Get selected channel index
    index = int(data.split(':')[2])
    channels = context.user_data.get('channel_results', [])
    
    if index >= len(channels):
        await query.edit_message_text("❌ Invalid selection. Please try again.")
        return ConversationHandler.END
    
    selected = channels[index]
    context.user_data['selected_channel'] = selected
    
    await query.edit_message_text("⏳ Loading channel info...")
    
    # Get full channel info
    channel_info = await get_channel_info(selected['url'])
    if channel_info:
        selected.update(channel_info)
        context.user_data['selected_channel'] = selected
    
    return await show_channel_preview(update, context, selected, edit=True)


async def show_channel_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    channel: dict,
    edit: bool = False
) -> int:
    """Show channel preview and ask for confirmation."""
    user_id = update.effective_user.id
    
    # Check if already subscribed
    existing = await get_subscription(user_id, channel['id'])
    if existing:
        message = f"⚠️ You're already subscribed to **{channel['name']}**!"
        
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        
        return ConversationHandler.END
    
    # Get recent videos
    recent_videos = await get_channel_videos(channel['url'], limit=3)
    
    preview = f"""
📺 **{channel['name']}**

"""
    
    if channel.get('subscriber_count'):
        from youtube.utils import format_views
        preview += f"👥 {format_views(channel['subscriber_count'])} subscribers\n"
    
    if recent_videos:
        preview += "\n**Recent videos:**\n"
        for video in recent_videos[:3]:
            short_icon = "🎬" if video.get('is_short') else "📺"
            preview += f"• {short_icon} {video['title'][:40]}...\n"
    
    preview += "\n**Subscribe to this channel?**"
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Subscribe", callback_data="sub:confirm"),
            InlineKeyboardButton("⭐ + Priority", callback_data="sub:confirm:priority"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="sub:cancel")],
    ])
    
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            preview, parse_mode='Markdown', reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            preview, parse_mode='Markdown', reply_markup=keyboard
        )
    
    return CONFIRMING


async def confirm_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm and save subscription."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data == 'sub:cancel':
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    
    is_priority = 'priority' in data
    channel = context.user_data.get('selected_channel')
    
    if not channel:
        await query.edit_message_text("❌ Error: Channel data lost. Please try again.")
        return ConversationHandler.END
    
    # Save subscription
    success = await add_subscription(
        user_id=user_id,
        channel_id=channel['id'],
        channel_name=channel['name'],
        channel_url=channel['url'],
        is_priority=is_priority
    )
    
    if success:
        # Mark existing videos and send notification for last 1 video
        await _process_new_subscription(user_id, channel, query.message.chat_id, context)
        
        priority_msg = " as a **priority channel** ⭐" if is_priority else ""
        await query.edit_message_text(
            f"✅ Subscribed to **{channel['name']}**{priority_msg}!\n\n"
            f"You'll receive notifications when new videos are posted.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            f"⚠️ You're already subscribed to **{channel['name']}**.",
            parse_mode='Markdown'
        )
    
    # Clear user data
    context.user_data.pop('selected_channel', None)
    context.user_data.pop('channel_results', None)
    
    return ConversationHandler.END


async def _process_new_subscription(user_id: int, channel: dict, chat_id: int, context) -> None:
    """
    Process new subscription:
    1. Mark all existing videos in channel_videos table (no notification)
    2. Send notification for only the last 1 video
    """
    from database import add_channel_video, log_notification
    from youtube.info import get_channel_videos
    from youtube.utils import format_views
    from tg_bot.keyboards import video_notification_keyboard
    
    try:
        # Get recent videos from channel
        videos = await get_channel_videos(channel['url'], limit=50)
        
        if not videos:
            return
        
        # Mark all videos as pre-subscription (add to channel_videos, log as notified)
        for video in videos[1:]:  # Skip the first (latest) video
            # Add to channel_videos
            await add_channel_video(
                channel_id=channel['id'],
                video_id=video['id'],
                title=video['title'],
                duration=video.get('duration', 0),
                is_short=video.get('is_short', False),
                upload_date=video.get('upload_date')
            )
            # Mark as already notified (so scheduler won't send)
            await log_notification(
                user_id=user_id,
                video_id=video['id'],
                channel_id=channel['id'],
                notification_type='pre_subscription'
            )
        
        # Send notification for only the LAST 1 video (first in list = most recent)
        if videos:
            latest_video = videos[0]
            
            # Add to channel_videos
            await add_channel_video(
                channel_id=channel['id'],
                video_id=latest_video['id'],
                title=latest_video['title'],
                duration=latest_video.get('duration', 0),
                is_short=latest_video.get('is_short', False),
                upload_date=latest_video.get('upload_date')
            )
            
            # Escape markdown special characters
            def escape_md(text):
                if not text:
                    return text
                for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
                    text = text.replace(char, f'\\{char}')
                return text
            
            safe_title = escape_md(latest_video['title'])
            safe_channel = escape_md(channel['name'])
            
            # Send notification for latest video
            message = (
                f"📺 **Latest from {safe_channel}!**\n\n"
                f"🎬 {safe_title}\n"
                f"👁️ {format_views(latest_video.get('view_count', 0))} views • ⏱️ {latest_video.get('duration_string', '')}\n\n"
                f"🔗 {latest_video.get('url', '')}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown',
                    reply_markup=video_notification_keyboard(latest_video['id'], channel['id'])
                )
                
                # Log notification
                await log_notification(
                    user_id=user_id,
                    video_id=latest_video['id'],
                    channel_id=channel['id'],
                    notification_type='subscription_welcome'
                )
            except Exception as e:
                logger.error(f"Error sending subscription welcome notification: {e}")
                
    except Exception as e:
        logger.error(f"Error processing new subscription: {e}")



async def cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the subscription flow."""
    await update.message.reply_text("❌ Cancelled.")
    context.user_data.pop('selected_channel', None)
    context.user_data.pop('channel_results', None)
    return ConversationHandler.END


async def quick_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str) -> None:
    """Quick subscribe from search results."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Get channel info
    from youtube.utils import build_channel_url
    channel_url = build_channel_url(channel_id)
    channel_info = await get_channel_info(channel_url)
    
    if not channel_info:
        await query.answer("❌ Could not get channel info", show_alert=True)
        return
    
    success = await add_subscription(
        user_id=user_id,
        channel_id=channel_info['id'],
        channel_name=channel_info['name'],
        channel_url=channel_info['url'],
        is_priority=False
    )
    
    if success:
        await query.answer(f"✅ Subscribed to {channel_info['name']}!")
    else:
        await query.answer("Already subscribed", show_alert=True)


# Conversation handler
subscribe_conversation = ConversationHandler(
    entry_points=[CommandHandler('subscribe', subscribe_command)],
    states={
        WAITING_QUERY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_query),
        ],
        SELECTING_CHANNEL: [
            CallbackQueryHandler(select_channel_callback, pattern=r'^sub:'),
        ],
        CONFIRMING: [
            CallbackQueryHandler(confirm_subscription, pattern=r'^sub:'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_subscription),
        CallbackQueryHandler(confirm_subscription, pattern=r'^sub:cancel'),
    ],
    name="subscribe",
    persistent=False,
)
