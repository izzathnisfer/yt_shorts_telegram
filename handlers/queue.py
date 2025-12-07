"""
Queue command handler - Watch later queue management.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_queue, remove_from_queue, clear_queue, add_to_queue
from youtube.info import get_video_info
from youtube.utils import format_duration
from tg_bot.keyboards import queue_keyboard, back_button


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /queue command."""
    # Check for subcommands
    if context.args:
        subcommand = context.args[0].lower()
        
        if subcommand == 'add' and len(context.args) > 1:
            url = context.args[1]
            await add_to_queue_command(update, context, url)
            return
        
        elif subcommand == 'clear':
            await clear_queue_command(update, context)
            return
    
    await show_queue(update, context)


async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show the watch queue."""
    user_id = update.effective_user.id
    queue_items = await get_queue(user_id)
    
    if update.callback_query:
        query = update.callback_query
        
        if not queue_items:
            await query.edit_message_text(
                "📥 **Watch Queue**\n\n"
                "Your queue is empty!\n\n"
                "Add videos with:\n"
                "• `/queue add <url>`\n"
                "• 📋 button on any video",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        total_duration = sum(item.get('duration', 0) for item in queue_items)
        
        message = f"📥 **Watch Queue** ({len(queue_items)} videos)\n"
        message += f"⏱️ Total: {format_duration(total_duration)}\n\n"
        message += "Tap to view, 🗑️ to remove:"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=queue_keyboard(queue_items, page)
        )
    else:
        if not queue_items:
            await update.message.reply_text(
                "📥 **Watch Queue**\n\n"
                "Your queue is empty!\n\n"
                "Add videos with:\n"
                "• `/queue add <url>`\n"
                "• 📋 button on any video",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        total_duration = sum(item.get('duration', 0) for item in queue_items)
        
        message = f"📥 **Watch Queue** ({len(queue_items)} videos)\n"
        message += f"⏱️ Total: {format_duration(total_duration)}\n\n"
        message += "Tap to view, 🗑️ to remove:"
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=queue_keyboard(queue_items, page)
        )


async def add_to_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """Add a video to queue from command."""
    user_id = update.effective_user.id
    
    loading = await update.message.reply_text("⏳ Getting video info...")
    
    info = await get_video_info(url)
    if not info:
        await loading.edit_text("❌ Could not get video info. Check the URL.")
        return
    
    success = await add_to_queue(
        user_id=user_id,
        video_id=info['id'],
        video_url=info['webpage_url'],
        title=info['title'],
        channel_name=info['channel_name'],
        duration=info['duration'],
        thumbnail_url=info.get('thumbnail')
    )
    
    if success:
        await loading.edit_text(
            f"📋 **Added to Queue!**\n\n"
            f"🎬 {info['title']}\n"
            f"📺 {info['channel_name']}\n"
            f"⏱️ {info['duration_string']}",
            parse_mode='Markdown'
        )
    else:
        await loading.edit_text("⚠️ Video is already in your queue.")


async def clear_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the entire queue."""
    user_id = update.effective_user.id
    count = await clear_queue(user_id)
    
    if count > 0:
        await update.message.reply_text(f"🗑️ Cleared {count} videos from your queue.")
    else:
        await update.message.reply_text("📥 Your queue was already empty.")


async def queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle queue callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    parts = data.split(':')
    action = parts[1]
    
    if action == 'page':
        page = int(parts[2])
        await show_queue(update, context, page)
    
    elif action == 'remove':
        video_id = parts[2]
        success = await remove_from_queue(user_id, video_id)
        if success:
            await query.answer("🗑️ Removed from queue")
        await show_queue(update, context)
    
    elif action == 'view':
        video_id = parts[2]
        queue_items = await get_queue(user_id)
        item = next((i for i in queue_items if i['video_id'] == video_id), None)
        
        if item:
            from tg_bot.keyboards import video_action_keyboard
            await query.edit_message_text(
                f"📺 **{item['title']}**\n\n"
                f"📺 {item['channel_name']}\n"
                f"⏱️ {format_duration(item['duration'])}",
                parse_mode='Markdown',
                reply_markup=video_action_keyboard(video_id, item.get('video_url', ''))
            )
    
    elif action == 'clear':
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await query.edit_message_text(
            "🗑️ **Clear Queue?**\n\n"
            "This will remove all videos from your queue.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Clear", callback_data="queue:do_clear"),
                    InlineKeyboardButton("❌ Cancel", callback_data="menu:queue"),
                ]
            ])
        )
    
    elif action == 'do_clear':
        count = await clear_queue(user_id)
        await query.edit_message_text(
            f"🗑️ Cleared {count} videos from your queue.",
            reply_markup=back_button()
        )
    
    elif action == 'sync':
        from handlers.sync import start_sync
        await start_sync(update, context)
    
    elif action == 'add':
        video_id = parts[2]
        from handlers.callbacks import handle_add_to_queue
        await handle_add_to_queue(update, context, video_id)
