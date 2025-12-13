"""
YouTube Shorts Bot - Main Entry Point

A Telegram bot that helps you consume YouTube content mindfully.
"""

import asyncio
import logging
import sys

from telegram import Update, BotCommand
from telegram.ext import Application

from tg_bot.bot import register_handlers, error_handler
from tg_bot.uploader import stop_client
from database import init_db, close_pool
from youtube.downloader import cleanup_downloads
from config import BOT_TOKEN

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

# Reduce noise from httpx and telegram libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Post-initialization callback."""
    logger.info("Starting YouTube Shorts Bot...")
    
    # Set bot commands
    commands = [
        BotCommand("start", "🏠 Main menu"),
        BotCommand("subscribe", "📺 Subscribe to a channel"),
        BotCommand("unsubscribe", "❌ Unsubscribe from a channel"),
        BotCommand("list", "📋 List subscribed channels"),
        BotCommand("search", "🔍 Search YouTube videos"),
        BotCommand("queue", "📥 View watch queue"),
        BotCommand("sync", "📲 Download all queued videos"),
        BotCommand("audio", "🎵 Download audio only"),
        BotCommand("lofi", "🎧 Get lofi music for studying"),
        BotCommand("focus", "🧘 Enable focus mode"),
        BotCommand("limit", "📊 Set daily watch limit"),
        BotCommand("stats", "📈 View your statistics"),
        BotCommand("favorites", "⭐ View favorite videos"),
        BotCommand("settings", "⚙️ Bot settings"),
        BotCommand("export", "💾 Export your data"),
        BotCommand("help", "❓ Help & commands"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set")
    
    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    
    # Cleanup old downloads
    logger.info("Cleaning up old downloads...")
    await cleanup_downloads(max_age_hours=24)
    
    logger.info("Startup complete! Bot is ready.")


async def post_shutdown(application: Application) -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down...")
    
    # Stop Pyrogram client
    await stop_client()
    
    # Close database pool
    await close_pool()
    
    logger.info("Shutdown complete!")


def main() -> None:
    """Run the bot."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    YouTube Shorts Bot                        ║
║          Your Mindful YouTube Companion 🧘                   ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Build application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Register handlers
    register_handlers(application)
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot
    logger.info("Starting bot polling...")
    application.run_polling(
        allowed_updates=['message', 'callback_query'],
        drop_pending_updates=True
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
