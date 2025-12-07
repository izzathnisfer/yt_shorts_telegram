"""
Nickname command handler - Set custom channel names.
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

from database import get_subscriptions, set_channel_nickname, get_subscription
from tg_bot.keyboards import back_button


SELECTING, ENTERING_NAME = range(2)


async def nickname_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /nickname command."""
    user_id = update.effective_user.id
    subscriptions = await get_subscriptions(user_id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📋 You have no subscriptions yet.\n\n"
            "Use /subscribe to add channels first.",
            reply_markup=back_button()
        )
        return ConversationHandler.END
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = []
    for sub in subscriptions[:10]:
        original = sub.get('channel_name', 'Unknown')
        nickname = sub.get('nickname')
        
        if nickname:
            display = f"{nickname} ({original})"
        else:
            display = original
        
        keyboard.append([
            InlineKeyboardButton(
                f"✏️ {display}",
                callback_data=f"nick:select:{sub['channel_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="nick:cancel")])
    
    await update.message.reply_text(
        "✏️ **Set Channel Nickname**\n\n"
        "Select a channel to rename:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SELECTING


async def select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle channel selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'nick:cancel':
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    
    channel_id = data.split(':')[2]
    user_id = update.effective_user.id
    
    sub = await get_subscription(user_id, channel_id)
    if not sub:
        await query.edit_message_text("❌ Channel not found.")
        return ConversationHandler.END
    
    context.user_data['nickname_channel'] = sub
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = []
    if sub.get('nickname'):
        keyboard.append([
            InlineKeyboardButton("🗑️ Remove Nickname", callback_data="nick:remove")
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="nick:cancel")])
    
    await query.edit_message_text(
        f"✏️ **Set Nickname**\n\n"
        f"Channel: {sub['channel_name']}\n"
        f"Current nickname: {sub.get('nickname') or '_None_'}\n\n"
        f"Send a new nickname for this channel:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ENTERING_NAME


async def receive_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and save nickname."""
    user_id = update.effective_user.id
    nickname = update.message.text.strip()[:50]  # Limit length
    
    channel = context.user_data.get('nickname_channel')
    if not channel:
        await update.message.reply_text("❌ Error: Channel data lost. Please try again.")
        return ConversationHandler.END
    
    await set_channel_nickname(user_id, channel['channel_id'], nickname)
    
    await update.message.reply_text(
        f"✅ Nickname set!\n\n"
        f"📺 {channel['channel_name']}\n"
        f"→ Now displays as: **{nickname}**",
        parse_mode='Markdown',
        reply_markup=back_button()
    )
    
    context.user_data.pop('nickname_channel', None)
    return ConversationHandler.END


async def remove_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove nickname callback."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    channel = context.user_data.get('nickname_channel')
    
    if channel:
        await set_channel_nickname(user_id, channel['channel_id'], None)
        await query.edit_message_text(
            f"✅ Nickname removed!\n\n"
            f"📺 Will display as: {channel['channel_name']}",
            reply_markup=back_button()
        )
    else:
        await query.edit_message_text("❌ Error. Please try again.")
    
    context.user_data.pop('nickname_channel', None)
    return ConversationHandler.END


async def cancel_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel nickname flow."""
    if update.callback_query:
        await update.callback_query.edit_message_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled.")
    
    context.user_data.pop('nickname_channel', None)
    return ConversationHandler.END


# Conversation handler
nickname_conversation = ConversationHandler(
    entry_points=[CommandHandler('nickname', nickname_command)],
    states={
        SELECTING: [
            CallbackQueryHandler(select_channel, pattern=r'^nick:select:'),
            CallbackQueryHandler(cancel_nickname, pattern=r'^nick:cancel'),
        ],
        ENTERING_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_nickname),
            CallbackQueryHandler(remove_nickname, pattern=r'^nick:remove'),
            CallbackQueryHandler(cancel_nickname, pattern=r'^nick:cancel'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_nickname),
        CallbackQueryHandler(cancel_nickname, pattern=r'^nick:cancel'),
    ],
    name="nickname",
    persistent=False,
)
