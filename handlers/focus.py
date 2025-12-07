"""
Focus command handler - Focus mode for distraction-free work.
"""

from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta

from database import set_focus_mode, is_in_focus_mode
from youtube.utils import parse_duration_string
from tg_bot.keyboards import back_button


async def focus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /focus command."""
    user_id = update.effective_user.id
    
    # Check current focus status
    is_focus, focus_end = await is_in_focus_mode(user_id)
    
    if context.args:
        arg = context.args[0].lower()
        
        # Turn off focus mode
        if arg == 'off':
            if is_focus:
                await set_focus_mode(user_id, None)
                await update.message.reply_text(
                    "✅ Focus mode disabled.\n\n"
                    "You'll receive notifications again.",
                    reply_markup=back_button()
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Focus mode is not active.",
                    reply_markup=back_button()
                )
            return
        
        # Parse duration
        duration_seconds = parse_duration_string(arg)
        
        if duration_seconds:
            end_time = datetime.now() + timedelta(seconds=duration_seconds)
            await set_focus_mode(user_id, end_time)
            
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            
            await update.message.reply_text(
                f"🧘 **Focus Mode Enabled**\n\n"
                f"Duration: {duration_str}\n"
                f"Ends at: {end_time.strftime('%I:%M %p')}\n\n"
                f"🔕 All notifications paused.\n"
                f"Use `/focus off` to disable early.\n\n"
                f"*Focus on what matters!*",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
    
    # Show status or usage
    if is_focus and focus_end:
        remaining = focus_end - datetime.now()
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes = remainder // 60
        remaining_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ End Focus Mode", callback_data="focus:off")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu:main")],
        ])
        
        await update.message.reply_text(
            f"🧘 **Focus Mode Active**\n\n"
            f"⏱️ Remaining: {remaining_str}\n"
            f"🕐 Ends at: {focus_end.strftime('%I:%M %p')}\n\n"
            f"🔕 Notifications are paused.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "🧘 **Focus Mode**\n\n"
            "Pause notifications to focus on work or study.\n\n"
            "Usage:\n"
            "• `/focus 2h` - Focus for 2 hours\n"
            "• `/focus 30m` - Focus for 30 minutes\n"
            "• `/focus off` - Turn off focus mode\n\n"
            "💡 *Tip: Use /lofi for study music!*",
            parse_mode='Markdown',
            reply_markup=back_button()
        )
