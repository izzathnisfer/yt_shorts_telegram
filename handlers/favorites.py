"""
Favorites command handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_favorites, remove_favorite
from youtube.utils import format_duration
from tg_bot.keyboards import favorites_keyboard, video_action_keyboard, back_button


async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /favorites command."""
    await show_favorites(update, context)


async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show favorites list."""
    user_id = update.effective_user.id
    favorites = await get_favorites(user_id)
    
    if update.callback_query:
        query = update.callback_query
        
        if not favorites:
            await query.edit_message_text(
                "⭐ **Favorites**\n\n"
                "No favorites yet!\n\n"
                "Tap ⭐ on any video to save it here.",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        await query.edit_message_text(
            f"⭐ **Favorites** ({len(favorites)})\n\n"
            "Tap to view, 🗑️ to remove:",
            parse_mode='Markdown',
            reply_markup=favorites_keyboard(favorites, page)
        )
    else:
        if not favorites:
            await update.message.reply_text(
                "⭐ **Favorites**\n\n"
                "No favorites yet!\n\n"
                "Tap ⭐ on any video to save it here.",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        
        await update.message.reply_text(
            f"⭐ **Favorites** ({len(favorites)})\n\n"
            "Tap to view, 🗑️ to remove:",
            parse_mode='Markdown',
            reply_markup=favorites_keyboard(favorites, page)
        )


async def favorites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle favorites callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    parts = data.split(':')
    action = parts[1]
    
    if action == 'page':
        page = int(parts[2])
        await show_favorites(update, context, page)
    
    elif action == 'view':
        video_id = parts[2]
        favorites = await get_favorites(user_id)
        fav = next((f for f in favorites if f['video_id'] == video_id), None)
        
        if fav:
            await query.edit_message_text(
                f"⭐ **{fav['title']}**\n\n"
                f"📺 {fav['channel_name']}\n"
                f"⏱️ {format_duration(fav.get('duration', 0))}",
                parse_mode='Markdown',
                reply_markup=video_action_keyboard(
                    video_id,
                    fav.get('video_url', ''),
                    show_favorite=False
                )
            )
        else:
            await show_favorites(update, context)
    
    elif action == 'remove':
        video_id = parts[2]
        success = await remove_favorite(user_id, video_id)
        if success:
            await query.answer("🗑️ Removed from favorites")
        await show_favorites(update, context)
    
    elif action == 'add':
        video_id = parts[2]
        from handlers.callbacks import handle_add_favorite
        await handle_add_favorite(update, context, video_id)
