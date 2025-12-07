"""
Limit command handler - Daily watch limit management.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_user_settings, update_user_settings, get_today_watch_count
from tg_bot.keyboards import limit_keyboard, back_button


async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /limit command."""
    user_id = update.effective_user.id
    settings = await get_user_settings(user_id)
    current_limit = settings.get('daily_limit', 20)
    today_count = await get_today_watch_count(user_id)
    
    # Set new limit
    if context.args:
        try:
            new_limit = int(context.args[0])
            if new_limit < 0:
                raise ValueError()
            
            await update_user_settings(user_id, daily_limit=new_limit)
            
            limit_text = "unlimited" if new_limit == 0 else str(new_limit)
            await update.message.reply_text(
                f"✅ Daily limit set to **{limit_text}**\n\n"
                f"📊 Today: {today_count}/{limit_text} videos",
                parse_mode='Markdown',
                reply_markup=back_button()
            )
            return
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid number. Use a positive number or 0 for unlimited.\n\n"
                "Example: `/limit 15`",
                parse_mode='Markdown'
            )
            return
    
    # Show current status
    limit_text = "unlimited" if current_limit == 0 else str(current_limit)
    
    if current_limit > 0:
        remaining = max(0, current_limit - today_count)
        percentage = (today_count / current_limit) * 100
        
        if percentage >= 100:
            status_emoji = "🛑"
            status_text = "Limit reached!"
        elif percentage >= 80:
            status_emoji = "⚠️"
            status_text = f"{remaining} remaining"
        else:
            status_emoji = "📊"
            status_text = f"{remaining} remaining"
        
        message = (
            f"{status_emoji} **Daily Watch Limit**\n\n"
            f"Today: **{today_count}/{limit_text}** videos\n"
            f"Status: {status_text}\n\n"
            f"Select a new limit:"
        )
    else:
        message = (
            f"📊 **Daily Watch Limit**\n\n"
            f"Current: **Unlimited**\n"
            f"Today: {today_count} videos\n\n"
            f"Select a limit:"
        )
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=limit_keyboard(current_limit)
    )
