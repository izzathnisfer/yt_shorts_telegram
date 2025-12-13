"""
Telegram bot setup using python-telegram-bot.
Handles handler registration only.
"""

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

logger = logging.getLogger(__name__)


def register_handlers(application: Application) -> None:
    """Register all command and message handlers."""
    
    # Import handlers here to avoid circular imports
    from handlers.start import start_command, menu_callback
    from handlers.help import help_command
    from handlers.subscribe import subscribe_conversation
    from handlers.unsubscribe import unsubscribe_command, unsubscribe_callback
    from handlers.list_channels import list_command
    from handlers.search import search_command, search_callback, text_search_handler
    from handlers.queue import queue_command, queue_callback
    from handlers.download import download_command
    from handlers.audio import audio_command
    from handlers.lofi import lofi_command, lofi_callback
    from handlers.settings import settings_command, settings_callback
    from handlers.focus import focus_command
    from handlers.limit import limit_command
    from handlers.priority import priority_command, priority_callback
    from handlers.nickname import nickname_conversation
    from handlers.sync import sync_command
    from handlers.stats import stats_command
    from handlers.favorites import favorites_command, favorites_callback
    from handlers.export_import import export_command, import_command, import_file_handler
    from handlers.callbacks import global_callback_handler
    from handlers.direct_link import youtube_url_handler
    
    # Leech feature imports
    from handlers.leech import leech_command, leech_nextcloud_command, leech_callback
    from handlers.leech_nextcloud import setnc_command, setnc_conversation
    from handlers.leech_admin import admin_command, admin_callback
    from handlers.z_command import num_command
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("audio", audio_command))
    application.add_handler(CommandHandler("lofi", lofi_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("focus", focus_command))
    application.add_handler(CommandHandler("limit", limit_command))
    application.add_handler(CommandHandler("priority", priority_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("favorites", favorites_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("import", import_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    
    # Leech command handlers
    application.add_handler(CommandHandler("l", leech_command))
    application.add_handler(CommandHandler("ld", leech_nextcloud_command))
    application.add_handler(CommandHandler("setnc", setnc_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("num", num_command))
    
    # Conversation handlers (must be added before generic callback handlers)
    application.add_handler(subscribe_conversation)
    application.add_handler(nickname_conversation)
    application.add_handler(setnc_conversation)  # NC settings conversation
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(search_callback, pattern=r"^search:"))
    application.add_handler(CallbackQueryHandler(queue_callback, pattern=r"^queue:"))
    application.add_handler(CallbackQueryHandler(lofi_callback, pattern=r"^lofi:"))
    application.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(priority_callback, pattern=r"^priority:"))
    application.add_handler(CallbackQueryHandler(favorites_callback, pattern=r"^fav:"))
    application.add_handler(CallbackQueryHandler(unsubscribe_callback, pattern=r"^unsub:"))
    
    # Leech callback handlers
    application.add_handler(CallbackQueryHandler(leech_callback, pattern=r"^leech:"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    
    application.add_handler(CallbackQueryHandler(global_callback_handler))
    
    # Message handlers
    application.add_handler(import_file_handler)  # Handle JSON file imports
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'(youtube\.com|youtu\.be)'),
        youtube_url_handler
    ))
    
    # Broadcast message handler (must be BEFORE text_search_handler)
    from handlers.leech_admin import handle_broadcast_message
    
    async def broadcast_or_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check for broadcast mode first, then fall back to search."""
        # Try broadcast first
        if await handle_broadcast_message(update, context):
            return
        # Fall back to search
        await text_search_handler(update, context)
    
    # Auto-search: any text message that's not a command or YouTube URL
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        broadcast_or_search
    ))
    
    logger.info("All handlers registered")


async def error_handler(update: Update, context) -> None:
    """Global error handler."""
    logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again later.\n"
                "If the problem persists, use /start to restart."
            )
        except Exception:
            pass
