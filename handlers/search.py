"""
Search command handler.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from youtube.search import search_videos
from youtube.utils import format_views
from tg_bot.keyboards import search_result_keyboard, back_button

logger = logging.getLogger(__name__)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search command."""
    # Check if query was provided
    if context.args:
        query = ' '.join(context.args)
        await perform_search(update, context, query)
    else:
        await update.message.reply_text(
            "🔍 **Search YouTube**\n\n"
            "Send me what you're looking for, or use:\n"
            "`/search your query here`",
            parse_mode='Markdown'
        )


async def text_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle plain text messages as search queries.
    This allows users to just type what they want to find.
    """
    if not update.message or not update.message.text:
        return
    
    query = update.message.text.strip()
    
    # Skip if empty or too short
    if len(query) < 2:
        return
    
    # Perform the search
    try:
        await perform_search(update, context, query)
    except Exception as e:
        logger.error(f"Search error for '{query}': {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Search failed: {str(e)[:100]}\n\nPlease try again.",
            parse_mode='Markdown'
        )


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Perform YouTube search and show results."""
    message = update.message or update.callback_query.message
    
    loading_msg = await message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
    
    results = await search_videos(query, limit=5)
    
    if not results:
        await loading_msg.edit_text(
            f"❌ No results found for: *{query}*\n\n"
            "Try different keywords.",
            parse_mode='Markdown',
            reply_markup=back_button()
        )
        return
    
    # Store results in context for callbacks
    context.user_data['search_results'] = results
    
    # Build results message
    text = f"🔍 **Search Results for:** _{query}_\n\n"
    
    keyboard = []
    for i, video in enumerate(results):
        short_icon = "🎬" if video.get('is_short') else "📺"
        title = video['title'][:45] + ('...' if len(video['title']) > 45 else '')
        
        text += f"{i+1}. {short_icon} **{title}**\n"
        text += f"   📺 {video['channel_name']} • {video['duration_string']}\n"
        text += f"   👁️ {video['view_count_string']} views\n\n"
        
        # Action buttons for each result
        keyboard.append([
            InlineKeyboardButton(f"{i+1}. 📥", callback_data=f"search:dl:{i}"),
            InlineKeyboardButton("🎵", callback_data=f"search:audio:{i}"),
            InlineKeyboardButton("📋", callback_data=f"search:queue:{i}"),
            InlineKeyboardButton("🔔", callback_data=f"search:sub:{i}"),
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    await loading_msg.edit_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle search result callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split(':')
    action = parts[1]
    index = int(parts[2])
    
    results = context.user_data.get('search_results', [])
    if index >= len(results):
        await query.answer("❌ Result expired. Please search again.", show_alert=True)
        return
    
    video = results[index]
    
    if action == 'dl':
        # Trigger download
        from handlers.callbacks import handle_video_download
        await handle_video_download(update, context, video['id'])
    
    elif action == 'audio':
        from handlers.callbacks import handle_audio_download
        await handle_audio_download(update, context, video['id'])
    
    elif action == 'queue':
        from handlers.callbacks import handle_add_to_queue
        await handle_add_to_queue(update, context, video['id'])
    
    elif action == 'sub':
        from handlers.subscribe import quick_subscribe
        await quick_subscribe(update, context, video.get('channel_id', ''))
