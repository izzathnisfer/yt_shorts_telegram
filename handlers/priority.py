"""
Priority command handler - Manage priority channels.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_subscriptions, set_channel_priority, get_subscription
from tg_bot.keyboards import back_button


async def priority_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /priority command."""
    user_id = update.effective_user.id
    subscriptions = await get_subscriptions(user_id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📋 You have no subscriptions yet.\n\n"
            "Use /subscribe to add channels first.",
            reply_markup=back_button()
        )
        return
    
    priority_channels = [s for s in subscriptions if s.get('is_priority')]
    regular_channels = [s for s in subscriptions if not s.get('is_priority')]
    
    message = "⭐ **Priority Channels**\n\n"
    message += "Priority channels:\n"
    message += "• Always notify immediately\n"
    message += "• Bypass quiet hours\n"
    message += "• Never batched\n\n"
    
    if priority_channels:
        message += f"**Current Priority ({len(priority_channels)}):**\n"
        for ch in priority_channels[:5]:
            name = ch.get('nickname') or ch.get('channel_name')
            message += f"⭐ {name}\n"
    else:
        message += "_No priority channels yet_\n"
    
    message += "\nTap to toggle priority:"
    
    keyboard = []
    for sub in subscriptions[:10]:
        name = sub.get('nickname') or sub.get('channel_name', 'Unknown')
        is_priority = sub.get('is_priority', False)
        icon = "⭐" if is_priority else "☆"
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {name}",
                callback_data=f"priority:toggle:{sub['channel_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle priority callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    parts = data.split(':')
    action = parts[1]
    
    if action == 'toggle':
        channel_id = parts[2]
        sub = await get_subscription(user_id, channel_id)
        
        if sub:
            current = sub.get('is_priority', False)
            await set_channel_priority(user_id, channel_id, not current)
            
            name = sub.get('nickname') or sub.get('channel_name')
            if current:
                await query.answer(f"☆ Removed priority from {name}")
            else:
                await query.answer(f"⭐ {name} is now priority!")
        
        # Refresh the list
        subscriptions = await get_subscriptions(user_id)
        
        keyboard = []
        for s in subscriptions[:10]:
            name = s.get('nickname') or s.get('channel_name', 'Unknown')
            is_priority = s.get('is_priority', False)
            icon = "⭐" if is_priority else "☆"
            keyboard.append([
                InlineKeyboardButton(
                    f"{icon} {name}",
                    callback_data=f"priority:toggle:{s['channel_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
        
        priority_count = sum(1 for s in subscriptions if s.get('is_priority'))
        message = f"⭐ **Priority Channels** ({priority_count})\n\nTap to toggle priority:"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif action in ['set', 'remove']:
        channel_id = parts[2]
        is_priority = action == 'set'
        await set_channel_priority(user_id, channel_id, is_priority)
        
        sub = await get_subscription(user_id, channel_id)
        name = sub.get('channel_name', 'Channel') if sub else 'Channel'
        
        await query.answer(f"✅ {'Set' if is_priority else 'Removed'} priority for {name}")
