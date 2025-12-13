"""
Nextcloud settings handler - Configure NC credentials.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

from services.leech_data import (
    get_nc_settings, update_nc_setting, initialize_user,
    DEFAULT_NC_DELETE_TIMER
)

logger = logging.getLogger(__name__)

# Conversation states
WAITING_URL = 1
WAITING_USER = 2
WAITING_PASS = 3
WAITING_TIMER = 4


def _settings_keyboard(user_id: int, settings: dict) -> InlineKeyboardMarkup:
    """Build Nextcloud settings keyboard."""
    nc_url = settings.get('link', 'NOTSET')
    nc_user = settings.get('user_name', 'NOTSET')
    nc_pass = settings.get('password', 'NOTSET')
    auto_delete = settings.get('nc_auto_delete', True)
    
    url_label = "✏️ Edit URL" if nc_url != 'NOTSET' else "➕ Set URL"
    user_label = "✏️ Edit Username" if nc_user != 'NOTSET' else "➕ Set Username"
    pass_label = "✏️ Edit Password" if nc_pass != 'NOTSET' else "➕ Set Password"
    delete_label = "🗑️ Disable Auto-Delete" if auto_delete else "🗑️ Enable Auto-Delete"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(url_label, callback_data=f"setnc:url:{user_id}")],
        [InlineKeyboardButton(user_label, callback_data=f"setnc:user:{user_id}")],
        [InlineKeyboardButton(pass_label, callback_data=f"setnc:pass:{user_id}")],
        [InlineKeyboardButton(delete_label, callback_data=f"setnc:toggledelete:{user_id}")],
        [InlineKeyboardButton("⏱️ Set Delete Timer", callback_data=f"setnc:timer:{user_id}")],
        [InlineKeyboardButton("❌ Close", callback_data=f"setnc:close:{user_id}")],
    ])


async def _show_settings(message, user_id: int, edit: bool = True) -> None:
    """Display Nextcloud settings menu."""
    settings = await get_nc_settings(user_id)
    
    nc_url = settings.get('link', 'NOTSET')
    nc_user = settings.get('user_name', 'NOTSET')
    nc_pass_display = '••••••••' if settings.get('password') and settings['password'] != 'NOTSET' else 'NOTSET'
    auto_delete = settings.get('nc_auto_delete', True)
    delete_timer = settings.get('nc_delete_timer', DEFAULT_NC_DELETE_TIMER)
    
    all_set = all(settings.get(k) and settings[k] != 'NOTSET' for k in ['link', 'user_name', 'password'])
    status_icon = "✅" if all_set else "⚠️"
    
    text = (
        f"{status_icon} **Nextcloud Settings**\n\n"
        f"**URL:** `{nc_url}`\n"
        f"**User:** `{nc_user}`\n"
        f"**Password:** `{nc_pass_display}`\n"
        f"**Auto-Delete:** {'✅ On' if auto_delete else '❌ Off'}\n"
        f"**Delete Timer:** `{delete_timer}` minutes\n\n"
        f"_(Use `/ld <url>` to upload to Nextcloud)_"
    )
    
    keyboard = _settings_keyboard(user_id, settings)
    
    if edit:
        await message.edit_text(text, parse_mode='Markdown', reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def setnc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setnc command - Open Nextcloud settings menu."""
    user_id = update.effective_user.id
    initialize_user(user_id)
    await _show_settings(update.message, user_id, edit=False)


async def setnc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Nextcloud settings callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split(":")
    
    if len(parts) < 3:
        return ConversationHandler.END
    
    option = parts[1]
    target_user_id = int(parts[2])
    user_id = query.from_user.id
    
    # Only owner can modify their settings
    if user_id != target_user_id:
        await query.answer("This is not your settings menu.", show_alert=True)
        return ConversationHandler.END
    
    if option == "close":
        await query.message.delete()
        return ConversationHandler.END
    
    elif option == "toggledelete":
        settings = await get_nc_settings(user_id)
        current = settings.get('nc_auto_delete', True)
        await update_nc_setting(user_id, 'nc_auto_delete', not current)
        await _show_settings(query.message, user_id)
        return ConversationHandler.END
    
    elif option == "url":
        context.user_data['setnc_msg'] = query.message
        await query.message.edit_text(
            "✏️ Send the **Nextcloud WebDAV URL**.\n\n"
            "Example: `https://cloud.example.com/remote.php/dav/files/username/`",
            parse_mode='Markdown'
        )
        return WAITING_URL
    
    elif option == "user":
        context.user_data['setnc_msg'] = query.message
        await query.message.edit_text(
            "👤 Send your **Nextcloud Username**.",
            parse_mode='Markdown'
        )
        return WAITING_USER
    
    elif option == "pass":
        context.user_data['setnc_msg'] = query.message
        await query.message.edit_text(
            "🔑 Send your **Nextcloud App Password**.\n\n"
            "_(Generate one in Nextcloud → Settings → Security → App Passwords)_",
            parse_mode='Markdown'
        )
        return WAITING_PASS
    
    elif option == "timer":
        context.user_data['setnc_msg'] = query.message
        await query.message.edit_text(
            "⏱️ Send the **Auto-Delete Timer** in minutes.\n\n"
            "Example: `30` (files deleted 30 min after upload)\n"
            "Use `0` to keep files forever.",
            parse_mode='Markdown'
        )
        return WAITING_TIMER
    
    return ConversationHandler.END


async def _receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Nextcloud URL input."""
    user_id = update.effective_user.id
    value = update.message.text.strip()
    
    if not value.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Invalid URL. Must start with `http://` or `https://`.", parse_mode='Markdown')
        return WAITING_URL
    
    # Ensure trailing slash
    if not value.endswith('/'):
        value += '/'
    
    await update_nc_setting(user_id, 'link', value)
    await update.message.delete()
    
    msg = context.user_data.get('setnc_msg')
    if msg:
        await _show_settings(msg, user_id)
    
    return ConversationHandler.END


async def _receive_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Nextcloud username input."""
    user_id = update.effective_user.id
    value = update.message.text.strip()
    
    await update_nc_setting(user_id, 'user_name', value)
    await update.message.delete()
    
    msg = context.user_data.get('setnc_msg')
    if msg:
        await _show_settings(msg, user_id)
    
    return ConversationHandler.END


async def _receive_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Nextcloud password input."""
    user_id = update.effective_user.id
    value = update.message.text.strip()
    
    await update_nc_setting(user_id, 'password', value)
    await update.message.delete()
    
    msg = context.user_data.get('setnc_msg')
    if msg:
        await _show_settings(msg, user_id)
    
    return ConversationHandler.END


async def _receive_timer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive auto-delete timer input."""
    user_id = update.effective_user.id
    value = update.message.text.strip()
    
    try:
        timer = int(value)
        if timer < 0:
            raise ValueError("Negative timer")
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Enter a positive integer.", parse_mode='Markdown')
        return WAITING_TIMER
    
    await update_nc_setting(user_id, 'nc_delete_timer', timer)
    await update.message.delete()
    
    msg = context.user_data.get('setnc_msg')
    if msg:
        await _show_settings(msg, user_id)
    
    return ConversationHandler.END


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    return ConversationHandler.END


# Conversation handler for NC settings
setnc_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(setnc_callback, pattern=r"^setnc:")
    ],
    states={
        WAITING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_url)],
        WAITING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_user)],
        WAITING_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_pass)],
        WAITING_TIMER: [MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_timer)],
    },
    fallbacks=[
        CallbackQueryHandler(setnc_callback, pattern=r"^setnc:close:")
    ],
    per_user=True,
    per_chat=True,
    per_message=False,
)
