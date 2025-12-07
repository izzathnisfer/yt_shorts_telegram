"""
List channels command handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_subscriptions
from tg_bot.keyboards import channel_list_keyboard, back_button


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command."""
    await show_channel_list(update, context)


async def show_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show subscribed channels list."""
    user_id = update.effective_user.id
    subscriptions = await get_subscriptions(user_id)
    
    if update.callback_query:
        query = update.callback_query
        
        if not subscriptions:
            await query.edit_message_text(
                "📋 **Your Subscriptions**\n\n"
                "You haven't subscribed to any channels yet.\n\n"
                "Use /subscribe to add channels!",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        count = len(subscriptions)
        priority_count = sum(1 for s in subscriptions if s.get('is_priority'))
        
        message = f"📋 **Your Subscriptions** ({count})\n"
        if priority_count:
            message += f"⭐ {priority_count} priority\n"
        message += "\nTap a channel to manage:"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=channel_list_keyboard(subscriptions, page)
        )
    else:
        if not subscriptions:
            await update.message.reply_text(
                "📋 **Your Subscriptions**\n\n"
                "You haven't subscribed to any channels yet.\n\n"
                "Use /subscribe to add channels!",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        count = len(subscriptions)
        priority_count = sum(1 for s in subscriptions if s.get('is_priority'))
        
        message = f"📋 **Your Subscriptions** ({count})\n"
        if priority_count:
            message += f"⭐ {priority_count} priority\n"
        message += "\nTap a channel to manage:"
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=channel_list_keyboard(subscriptions, page)
        )
