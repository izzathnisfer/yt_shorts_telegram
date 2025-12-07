"""
Stats command handler - View watching statistics.
"""

from telegram import Update
from telegram.ext import ContextTypes

from database import get_daily_stats, get_weekly_stats, get_all_time_stats, get_user_settings
from youtube.utils import format_duration_long
from tg_bot.keyboards import back_button


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command."""
    await show_stats(update, context)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics."""
    user_id = update.effective_user.id
    
    # Get all stats
    today = await get_daily_stats(user_id)
    weekly = await get_weekly_stats(user_id)
    all_time = await get_all_time_stats(user_id)
    settings = await get_user_settings(user_id)
    
    limit = settings.get('daily_limit', 20)
    limit_text = "∞" if limit == 0 else str(limit)
    
    # Format today
    today_videos = today['videos_watched'] + today['shorts_watched']
    today_duration = format_duration_long(today['total_duration'])
    
    # Format weekly
    weekly_videos = weekly['videos_watched'] + weekly['shorts_watched']
    weekly_duration = format_duration_long(weekly['total_duration'])
    weekly_lofi = format_duration_long(weekly['lofi_duration'])
    
    # Format all time
    all_videos = all_time['videos_watched'] + all_time['shorts_watched']
    all_duration = format_duration_long(all_time['total_duration'])
    
    # Estimate time saved (assume 30 min saved per 5 videos by avoiding scrolling)
    estimated_saved = (all_videos // 5) * 30  # minutes
    saved_str = format_duration_long(estimated_saved * 60)
    
    message = f"""
📊 **Your Statistics**

**Today** ({today_videos}/{limit_text})
├ 📺 Videos: {today['videos_watched']}
├ 🎬 Shorts: {today['shorts_watched']}
├ 🎧 Lofi: {today['lofi_sessions']} sessions
└ ⏱️ Time: {today_duration}

**This Week**
├ 📺 Videos: {weekly['videos_watched']}
├ 🎬 Shorts: {weekly['shorts_watched']}
├ 🎧 Lofi: {weekly_lofi}
└ ⏱️ Total: {weekly_duration}

"""
    
    # Top channels
    if weekly.get('top_channels'):
        message += "**Top Channels (by time):**\n"
        for i, ch in enumerate(weekly['top_channels'][:5], 1):
            duration = format_duration_long(ch['duration'])
            message += f"{i}. {ch['channel_name']} - {ch['videos']} videos ({duration})\n"
        message += "\n"
    
    message += f"""
**All Time**
├ 📺 Total: {all_videos} videos
└ ⏱️ Time: {all_duration}

💪 **Estimated saved: ~{saved_str}**
_by avoiding YouTube scrolling!_
"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=back_button()
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=back_button()
        )
