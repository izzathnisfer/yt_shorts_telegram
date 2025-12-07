"""
Message templates for the bot.
Centralized formatting for consistent user experience.
"""

from youtube.utils import format_views, format_duration, format_duration_long


def welcome_message(today_count: int, limit: int, is_focus: bool = False, focus_remaining: str = None) -> str:
    """Generate welcome message."""
    message = """
🎬 **YouTube Shorts Bot**

Your mindful YouTube companion. Get your favorite content
delivered here — without the endless scroll.

🧘 *Watch intentionally, not compulsively.*

━━━━━━━━━━━━━━━━━━━━━
"""
    
    if is_focus and focus_remaining:
        message += f"""
🧘 **Focus Mode Active**
Notifications paused. Remaining: {focus_remaining}

"""
    
    if limit > 0:
        message += f"📊 Today: {today_count}/{limit} videos\n"
    else:
        message += f"📊 Today: {today_count} videos\n"
    
    message += "\nWhat would you like to do?"
    
    return message


def new_short_caption(title: str, channel_name: str, duration_str: str) -> str:
    """Caption for auto-sent shorts."""
    return (
        f"🎬 **New Short from {channel_name}!**\n\n"
        f"{title}\n"
        f"⏱️ {duration_str}"
    )


def new_video_notification(
    title: str,
    channel_name: str,
    view_count: int,
    duration_str: str,
    url: str
) -> str:
    """Message for new video notification."""
    return (
        f"📺 **New from {channel_name}!**\n\n"
        f"🎬 {title}\n"
        f"👁️ {format_views(view_count)} views • ⏱️ {duration_str}\n\n"
        f"🔗 {url}"
    )


def video_preview(
    title: str,
    channel_name: str,
    view_count: int,
    duration_str: str,
    is_short: bool = False
) -> str:
    """Preview message before download."""
    icon = "🎬 Short" if is_short else "📺 Video"
    return f"""
{icon} **{title}**

📺 {channel_name}
👁️ {format_views(view_count)} views
⏱️ {duration_str}

What would you like to do?
"""


def video_sent_caption(title: str, channel_name: str, duration_str: str) -> str:
    """Caption for sent video."""
    return (
        f"🎬 **{title}**\n\n"
        f"📺 {channel_name}\n"
        f"⏱️ {duration_str}"
    )


def audio_sent_caption(title: str, channel_name: str) -> str:
    """Caption for sent audio."""
    return f"🎵 **{title}**\n📺 {channel_name}"


def lofi_caption(title: str, duration_minutes: int) -> str:
    """Caption for lofi music."""
    return (
        f"🎧 **Lofi Study Music**\n\n"
        f"🎵 {title}\n"
        f"⏱️ {format_duration_long(duration_minutes * 60)}\n\n"
        f"🧘 *Focus and study well!*"
    )


def daily_limit_warning(current: int, limit: int) -> str:
    """Warning when approaching daily limit."""
    remaining = limit - current
    return (
        f"⚠️ Heads up! You've watched {current}/{limit} videos today.\n\n"
        f"{remaining} videos remaining. Watch mindfully! 🧘"
    )


def daily_limit_reached(limit: int) -> str:
    """Message when daily limit is reached."""
    return (
        f"🛑 **Daily limit reached!**\n\n"
        f"You've watched {limit}/{limit} videos today.\n"
        f"Limit resets at midnight.\n\n"
        f"Take a break. Touch grass. 🌿"
    )


def duplicate_warning(title: str, date_str: str) -> str:
    """Warning for duplicate video."""
    return (
        f"⚠️ **Already Downloaded!**\n\n"
        f"You downloaded this video on {date_str}.\n\n"
        f"🎬 {title}"
    )


def weekly_report(
    videos_watched: int,
    shorts_watched: int,
    total_duration: int,
    lofi_duration: int,
    top_channels: list
) -> str:
    """Weekly statistics report."""
    total_videos = videos_watched + shorts_watched
    
    message = f"""
📊 **Weekly Report**

**This Week:**
├ 📺 {total_videos} videos watched
├ 🎬 {shorts_watched} shorts
├ 🎧 {format_duration_long(lofi_duration)} of lofi music
├ ⏱️ {format_duration_long(total_duration)} total
└ 💪 ~{format_duration_long((total_videos // 5) * 30 * 60)} saved vs YouTube scrolling!

"""
    
    if top_channels:
        message += "**Top Channels (by time spent):**\n"
        for i, ch in enumerate(top_channels[:5], 1):
            duration = format_duration_long(ch['duration'])
            message += f"{i}. {ch['channel_name']} - {ch['videos']} videos ({duration})\n"
    
    message += "\n🎯 Keep it intentional!"
    
    return message


def stats_message(
    today_videos: int,
    today_shorts: int,
    today_duration: int,
    weekly_videos: int,
    weekly_shorts: int,
    weekly_duration: int,
    weekly_lofi: int,
    all_time_videos: int,
    all_time_duration: int,
    top_channels: list,
    daily_limit: int
) -> str:
    """Full statistics message."""
    limit_text = "∞" if daily_limit == 0 else str(daily_limit)
    today_total = today_videos + today_shorts
    weekly_total = weekly_videos + weekly_shorts
    estimated_saved = (all_time_videos // 5) * 30
    
    message = f"""
📊 **Your Statistics**

**Today** ({today_total}/{limit_text})
├ 📺 Videos: {today_videos}
├ 🎬 Shorts: {today_shorts}
└ ⏱️ Time: {format_duration_long(today_duration)}

**This Week**
├ 📺 Videos: {weekly_videos}
├ 🎬 Shorts: {weekly_shorts}
├ 🎧 Lofi: {format_duration_long(weekly_lofi)}
└ ⏱️ Total: {format_duration_long(weekly_duration)}

"""
    
    if top_channels:
        message += "**Top Channels (by time):**\n"
        for i, ch in enumerate(top_channels[:5], 1):
            duration = format_duration_long(ch['duration'])
            message += f"{i}. {ch['channel_name']} - {ch['videos']} videos ({duration})\n"
        message += "\n"
    
    message += f"""
**All Time**
├ 📺 Total: {all_time_videos} videos
└ ⏱️ Time: {format_duration_long(all_time_duration)}

💪 **Estimated saved: ~{format_duration_long(estimated_saved * 60)}**
_by avoiding YouTube scrolling!_
"""
    
    return message


def focus_mode_enabled(duration_str: str, end_time_str: str) -> str:
    """Focus mode enabled message."""
    return (
        f"🧘 **Focus Mode Enabled**\n\n"
        f"Duration: {duration_str}\n"
        f"Ends at: {end_time_str}\n\n"
        f"🔕 All notifications paused.\n"
        f"Use `/focus off` to disable early.\n\n"
        f"*Focus on what matters!*"
    )


def focus_mode_status(remaining_str: str, end_time_str: str) -> str:
    """Focus mode status message."""
    return (
        f"🧘 **Focus Mode Active**\n\n"
        f"⏱️ Remaining: {remaining_str}\n"
        f"🕐 Ends at: {end_time_str}\n\n"
        f"🔕 Notifications are paused."
    )
