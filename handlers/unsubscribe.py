"""
Unsubscribe command handler.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_subscriptions, remove_subscription, get_subscription
from tg_bot.keyboards import back_button


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unsubscribe command."""
    user_id = update.effective_user.id
    subscriptions = await get_subscriptions(user_id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📋 You have no subscriptions yet.\n\n"
            "Use /subscribe to add channels.",
            reply_markup=back_button()
        )
        return
    
    keyboard = []
    for sub in subscriptions[:10]:  # Limit to 10
        name = sub.get('nickname') or sub.get('channel_name', 'Unknown')
        priority = "⭐ " if sub.get('is_priority') else ""
        keyboard.append([
            InlineKeyboardButton(
                f"{priority}{name}",
                callback_data=f"unsub:confirm:{sub['channel_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    await update.message.reply_text(
        "🗑️ **Unsubscribe from a Channel**\n\n"
        "Select a channel to unsubscribe:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def unsubscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unsubscribe callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith('unsub:confirm:'):
        channel_id = data.split(':')[2]
        sub = await get_subscription(user_id, channel_id)
        
        if not sub:
            await query.edit_message_text("❌ Subscription not found.")
            return
        
        name = sub.get('nickname') or sub.get('channel_name', 'Unknown')
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Unsubscribe", callback_data=f"unsub:do:{channel_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="menu:list"),
            ]
        ])
        
        await query.edit_message_text(
            f"🗑️ **Unsubscribe from {name}?**\n\n"
            f"You will no longer receive notifications from this channel.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    elif data.startswith('unsub:do:'):
        channel_id = data.split(':')[2]
        sub = await get_subscription(user_id, channel_id)
        name = sub.get('channel_name', 'Unknown') if sub else 'Unknown'
        
        success = await remove_subscription(user_id, channel_id)
        
        if success:
            await query.edit_message_text(
                f"✅ Unsubscribed from **{name}**.",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
        else:
            await query.edit_message_text(
                "❌ Could not unsubscribe. Please try again.",
                reply_markup=back_button()
            )
