"""
Settings command handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_user_settings, update_user_settings
from tg_bot.keyboards import (
    settings_keyboard, interval_keyboard, resolution_keyboard,
    limit_keyboard, back_button
)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command."""
    await show_settings(update, context)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    user_id = update.effective_user.id
    settings = await get_user_settings(user_id)
    
    message = "⚙️ **Settings**\n\nTap an option to change:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=settings_keyboard(settings)
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=settings_keyboard(settings)
        )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle settings callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    parts = data.split(':')
    action = parts[1]
    
    settings = await get_user_settings(user_id)
    
    # Show sub-menus
    if action == 'interval':
        await query.edit_message_text(
            "⏱️ **Check Interval**\n\n"
            "How often should I check for new videos?",
            parse_mode='Markdown',
            reply_markup=interval_keyboard(settings.get('check_interval', 15))
        )
    
    elif action == 'resolution':
        await query.edit_message_text(
            "📺 **Video Resolution**\n\n"
            "Choose preferred download quality:",
            parse_mode='Markdown',
            reply_markup=resolution_keyboard(settings.get('resolution', '720'))
        )
    
    elif action == 'limit':
        await query.edit_message_text(
            "📊 **Daily Watch Limit**\n\n"
            "Maximum videos per day:",
            parse_mode='Markdown',
            reply_markup=limit_keyboard(settings.get('daily_limit', 20))
        )
    
    elif action == 'quiet':
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        quiet_start = settings.get('quiet_start', '23:00')
        quiet_end = settings.get('quiet_end', '07:00')
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌅 Start: " + quiet_start, callback_data="settings:set_quiet_start"),
                InlineKeyboardButton("🌄 End: " + quiet_end, callback_data="settings:set_quiet_end"),
            ],
            [InlineKeyboardButton("❌ Disable Quiet Hours", callback_data="settings:disable_quiet")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu:settings")],
        ])
        
        await query.edit_message_text(
            "🌙 **Quiet Hours**\n\n"
            f"Current: {quiet_start} - {quiet_end}\n\n"
            "No notifications during quiet hours\n"
            "(except priority channels).",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    elif action == 'auto_shorts':
        current = settings.get('auto_download_shorts', True)
        await update_user_settings(user_id, auto_download_shorts=not current)
        await show_settings(update, context)
    
    elif action == 'timezone':
        # For now, just show current timezone
        tz = settings.get('timezone', 'Asia/Kolkata')
        await query.edit_message_text(
            f"🕐 **Timezone**\n\n"
            f"Current: {tz}\n\n"
            f"To change, use:\n`/settings timezone Asia/Tokyo`",
            parse_mode='Markdown',
            reply_markup=back_button("menu:settings")
        )
    
    # Set values
    elif action == 'set_interval':
        value = int(parts[2])
        await update_user_settings(user_id, check_interval=value)
        await query.answer(f"✅ Check interval set to {value} minutes")
        await show_settings(update, context)
    
    elif action == 'set_resolution':
        value = parts[2]
        await update_user_settings(user_id, resolution=value)
        await query.answer(f"✅ Resolution set to {value}p")
        await show_settings(update, context)
    
    elif action == 'set_limit':
        value = int(parts[2])
        await update_user_settings(user_id, daily_limit=value)
        limit_text = "unlimited" if value == 0 else str(value)
        await query.answer(f"✅ Daily limit set to {limit_text}")
        await show_settings(update, context)
    
    elif action == 'disable_quiet':
        await update_user_settings(user_id, quiet_start=None, quiet_end=None)
        await query.answer("✅ Quiet hours disabled")
        await show_settings(update, context)
    
    elif action == 'nextcloud':
        from handlers.leech_nextcloud import setnc_command
        # Redirect to setnc settings by calling the command handler
        await query.answer()
        await query.message.edit_text(
            "☁️ **Nextcloud Settings**\n\n"
            "Use `/setnc` to configure your Nextcloud:\n"
            "• WebDAV URL\n"
            "• Username\n"
            "• App Password\n"
            "• Auto-delete timer",
            parse_mode='Markdown',
            reply_markup=back_button("menu:settings")
        )
