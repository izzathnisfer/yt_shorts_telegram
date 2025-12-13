"""
Start command handler - Main menu and welcome message.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_or_create_user, get_user_settings, is_in_focus_mode, get_today_watch_count
from tg_bot.keyboards import main_menu_keyboard


WELCOME_MESSAGE = """
🎬 **YouTube Shorts Bot**

Your mindful YouTube companion. Get your favorite content
delivered here — without the endless scroll.

🧘 *Watch intentionally, not compulsively.*

━━━━━━━━━━━━━━━━━━━━━
"""

FOCUS_MODE_NOTICE = """
🧘 **Focus Mode Active**
You're currently focusing. Notifications paused.
Remaining: {remaining}

"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    
    # Get or create user in database
    await get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Check focus mode
    is_focus, focus_end = await is_in_focus_mode(user.id)
    
    message = WELCOME_MESSAGE
    
    if is_focus and focus_end:
        from datetime import datetime
        remaining = focus_end - datetime.now()
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes = remainder // 60
        remaining_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
        message += FOCUS_MODE_NOTICE.format(remaining=remaining_str)
    
    # Get today's stats
    settings = await get_user_settings(user.id)
    today_count = await get_today_watch_count(user.id)
    limit = settings.get('daily_limit', 20)
    
    if limit > 0:
        message += f"📊 Today: {today_count}/{limit} videos\n"
    else:
        message += f"📊 Today: {today_count} videos\n"
    
    message += "\nWhat would you like to do?"
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu button callbacks."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split(':')[1]
    
    if action == 'main':
        user = update.effective_user
        
        is_focus, focus_end = await is_in_focus_mode(user.id)
        message = WELCOME_MESSAGE
        
        if is_focus and focus_end:
            from datetime import datetime
            remaining = focus_end - datetime.now()
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            remaining_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            message += FOCUS_MODE_NOTICE.format(remaining=remaining_str)
        
        settings = await get_user_settings(user.id)
        today_count = await get_today_watch_count(user.id)
        limit = settings.get('daily_limit', 20)
        
        if limit > 0:
            message += f"📊 Today: {today_count}/{limit} videos\n"
        else:
            message += f"📊 Today: {today_count} videos\n"
        
        message += "\nWhat would you like to do?"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    
    elif action == 'subscribe':
        await query.edit_message_text(
            "📺 **Subscribe to a Channel**\n\n"
            "Send me a channel name or YouTube URL to subscribe.\n\n"
            "Examples:\n"
            "• `MKBHD`\n"
            "• `https://youtube.com/@MKBHD`\n"
            "• `https://youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ`",
            parse_mode='Markdown'
        )
        context.user_data['expecting'] = 'subscribe_query'
    
    elif action == 'list':
        from handlers.list_channels import show_channel_list
        await show_channel_list(update, context)
    
    elif action == 'search':
        await query.edit_message_text(
            "🔍 **Search YouTube**\n\n"
            "Send me what you're looking for, or use:\n"
            "`/search your query here`",
            parse_mode='Markdown'
        )
        context.user_data['expecting'] = 'search_query'
    
    elif action == 'queue':
        from handlers.queue import show_queue
        await show_queue(update, context)
    
    elif action == 'lofi':
        from handlers.lofi import show_lofi_menu
        await show_lofi_menu(update, context)
    
    elif action == 'favorites':
        from handlers.favorites import show_favorites
        await show_favorites(update, context)
    
    elif action == 'stats':
        from handlers.stats import show_stats
        await show_stats(update, context)
    
    elif action == 'settings':
        from handlers.settings import show_settings
        await show_settings(update, context)
    
    elif action == 'help':
        from handlers.help import show_help
        await show_help(update, context)
    
    elif action == 'leech':
        await query.edit_message_text(
            "📥 **Leech URL**\n\n"
            "Download files from any direct URL:\n\n"
            "• `/l <url>` - Upload to Telegram\n"
            "• `/ld <url>` - Upload to Nextcloud\n\n"
            "⚙️ Configure Nextcloud with `/setnc`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Nextcloud Settings", callback_data="settings:nextcloud")],
                [InlineKeyboardButton("🔙 Back", callback_data="menu:main")]
            ])
        )
