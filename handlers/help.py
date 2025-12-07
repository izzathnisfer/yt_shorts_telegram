"""
Help command handler - Command reference.
"""

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.keyboards import back_button


HELP_MESSAGE = """
❓ **Help & Commands**

━━━━━━━━━━━━━━━━━━━━━

**📺 Content**
• `/subscribe` - Subscribe to a YouTube channel
• `/unsubscribe` - Unsubscribe from a channel
• `/list` - View your subscribed channels
• `/search <query>` - Search YouTube videos
• `/download <url>` - Download a video
• `/download <url> 1:30-5:00` - Download trimmed
• `/audio <url>` - Download audio only (MP3)

**📥 Queue & Favorites**
• `/queue` - View your watch queue
• `/queue add <url>` - Add video to queue
• `/sync` - Download all queued videos
• `/favorites` - View favorite videos

**🎧 Focus & Lofi**
• `/lofi` or `/lofi 2h` - Get lofi study music
• `/focus 2h` - Enable focus mode (no notifications)
• `/focus off` - Disable focus mode

**📊 Stats & Limits**
• `/stats` - View your watching statistics
• `/limit` - View/set daily watch limit
• `/limit 15` - Set limit to 15 videos/day

**⚙️ Settings**
• `/settings` - All preferences
• `/priority` - Manage priority channels
• `/nickname` - Set channel nicknames
• `/export` - Export your data (backup)
• `/import` - Restore from backup

**💡 Tips**
• Send any YouTube link to download it directly
• Priority channels bypass quiet hours
• Weekly reports are sent every Sunday
• Use the queue for intentional viewing!

━━━━━━━━━━━━━━━━━━━━━

🧘 *Remember: Watch intentionally!*
"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode='Markdown',
        reply_markup=back_button()
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help in callback context."""
    query = update.callback_query
    
    await query.edit_message_text(
        HELP_MESSAGE,
        parse_mode='Markdown',
        reply_markup=back_button()
    )
