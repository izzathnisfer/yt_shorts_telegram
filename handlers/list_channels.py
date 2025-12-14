"""
List channels command handler with pagination and channel management.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_subscriptions, get_subscription
from tg_bot.keyboards import channel_manage_keyboard, back_button


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command."""
    await show_channel_list(update, context, page=0)


async def show_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show subscribed channels list with numbered buttons."""
    user_id = update.effective_user.id
    subscriptions = await get_subscriptions(user_id)
    
    # Store subscriptions in context for callback access
    context.user_data['channel_list'] = subscriptions
    
    # Build message and keyboard
    text, keyboard = _build_channel_list(subscriptions, page)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )


def _build_channel_list(subscriptions: list, page: int = 0, page_size: int = 8) -> tuple:
    """Build channel list message and keyboard."""
    if not subscriptions:
        text = (
            "📋 **Your Subscriptions**\n\n"
            "You haven't subscribed to any channels yet.\n\n"
            "Use /subscribe to add channels!"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Subscribe", callback_data="menu:subscribe")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu:main")]
        ])
        return text, keyboard
    
    count = len(subscriptions)
    priority_count = sum(1 for s in subscriptions if s.get('is_priority'))
    
    # Calculate pagination
    total_pages = (count + page_size - 1) // page_size
    start = page * page_size
    end = min(start + page_size, count)
    page_channels = subscriptions[start:end]
    
    # Build message with numbered list
    text = f"📋 **Your Subscriptions** ({count})\n"
    if priority_count:
        text += f"⭐ {priority_count} priority\n"
    text += f"\n_Page {page + 1}/{total_pages}_\n\n"
    
    for i, channel in enumerate(page_channels, start=start + 1):
        priority_icon = "⭐ " if channel.get('is_priority') else ""
        name = channel.get('nickname') or channel.get('channel_name', 'Unknown')
        # Escape markdown in channel names
        name = name.replace('_', '\\_').replace('*', '\\*')
        text += f"`{i}.` {priority_icon}{name}\n"
    
    text += "\n_Tap a number to manage:_"
    
    # Build keyboard with numbered buttons (grid layout)
    keyboard = []
    
    # Number buttons in rows of 4
    row = []
    for i, _ in enumerate(page_channels, start=start + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"channels:{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"channels:page:{page - 1}"))
    if end < count:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"channels:page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Action row
    keyboard.append([
        InlineKeyboardButton("➕ Add", callback_data="menu:subscribe"),
        InlineKeyboardButton("🔙 Back", callback_data="menu:main"),
    ])
    
    return text, InlineKeyboardMarkup(keyboard)


async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle channel list callbacks (pagination and channel selection)."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # Handle pagination
    if data.startswith("channels:page:"):
        page = int(data.split(":")[2])
        subscriptions = await get_subscriptions(user_id)
        context.user_data['channel_list'] = subscriptions
        
        text, keyboard = _build_channel_list(subscriptions, page)
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    # Handle channel selection by index
    elif data.startswith("channels:") and data.split(":")[1].isdigit():
        index = int(data.split(":")[1]) - 1  # Convert to 0-based
        
        # Get subscriptions from context or refresh
        subscriptions = context.user_data.get('channel_list')
        if not subscriptions:
            subscriptions = await get_subscriptions(user_id)
            context.user_data['channel_list'] = subscriptions
        
        if 0 <= index < len(subscriptions):
            channel = subscriptions[index]
            await show_channel_details(query, channel)
        else:
            await query.answer("Channel not found", show_alert=True)


async def show_channel_details(query, channel: dict) -> None:
    """Show channel management screen."""
    name = channel.get('nickname') or channel.get('channel_name', 'Unknown')
    channel_id = channel.get('channel_id')
    is_priority = channel.get('is_priority', False)
    
    # Escape markdown
    safe_name = name.replace('_', '\\_').replace('*', '\\*')
    
    text = f"📺 **{safe_name}**\n\n"
    
    if channel.get('nickname'):
        original = channel.get('channel_name', '')
        safe_original = original.replace('_', '\\_').replace('*', '\\*')
        text += f"_Original: {safe_original}_\n"
    
    if is_priority:
        text += "⭐ **Priority Channel**\n"
    
    text += "\nChoose an action:"
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=channel_manage_keyboard(channel_id, is_priority)
    )
