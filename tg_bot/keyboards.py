"""
Reusable inline keyboard builders for the bot.
Provides consistent UI components across all handlers.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Optional


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📺 Subscribe", callback_data="menu:subscribe"),
            InlineKeyboardButton("📋 My Channels", callback_data="menu:list"),
        ],
        [
            InlineKeyboardButton("🔍 Search", callback_data="menu:search"),
            InlineKeyboardButton("📥 Queue", callback_data="menu:queue"),
        ],
        [
            InlineKeyboardButton("🎧 Lofi Music", callback_data="menu:lofi"),
            InlineKeyboardButton("⭐ Favorites", callback_data="menu:favorites"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="menu:stats"),
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="menu:help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_button(callback_data: str = "menu:main") -> InlineKeyboardMarkup:
    """Single back button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data=callback_data)]
    ])


def confirm_cancel_keyboard(
    confirm_data: str,
    cancel_data: str = "menu:main"
) -> InlineKeyboardMarkup:
    """Confirm/Cancel buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_data),
        ]
    ])


def video_action_keyboard(
    video_id: str,
    video_url: str,
    show_download: bool = True,
    show_audio: bool = True,
    show_queue: bool = True,
    show_favorite: bool = True,
    show_skip: bool = True,
    show_subscribe: bool = False,
    channel_id: str = None,
) -> InlineKeyboardMarkup:
    """Video action buttons."""
    keyboard = []
    
    # First row: Main actions
    row1 = []
    if show_download:
        row1.append(InlineKeyboardButton("📥 Download", callback_data=f"dl:video:{video_id}"))
    if show_audio:
        row1.append(InlineKeyboardButton("🎵 Audio", callback_data=f"dl:audio:{video_id}"))
    if row1:
        keyboard.append(row1)
    
    # Second row: Queue and Favorite
    row2 = []
    if show_queue:
        row2.append(InlineKeyboardButton("📋 Queue", callback_data=f"queue:add:{video_id}"))
    if show_favorite:
        row2.append(InlineKeyboardButton("⭐ Favorite", callback_data=f"fav:add:{video_id}"))
    if row2:
        keyboard.append(row2)
    
    # Third row: Secondary actions
    row3 = []
    if show_subscribe and channel_id:
        row3.append(InlineKeyboardButton("🔔 Subscribe", callback_data=f"sub:add:{channel_id}"))
    if show_skip:
        row3.append(InlineKeyboardButton("⏭️ Skip", callback_data=f"skip:{video_id}"))
    if row3:
        keyboard.append(row3)
    
    return InlineKeyboardMarkup(keyboard)


def video_notification_keyboard(
    video_id: str,
    channel_id: str,
) -> InlineKeyboardMarkup:
    """Keyboard for new video notifications from subscriptions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download", callback_data=f"dl:video:{video_id}"),
            InlineKeyboardButton("🎵 Audio", callback_data=f"dl:audio:{video_id}"),
        ],
        [
            InlineKeyboardButton("📋 Queue", callback_data=f"queue:add:{video_id}"),
            InlineKeyboardButton("⭐ Favorite", callback_data=f"fav:add:{video_id}"),
        ],
        [
            InlineKeyboardButton("⏭️ Skip", callback_data=f"skip:{video_id}"),
            InlineKeyboardButton("🗑️ Unsubscribe", callback_data=f"unsub:confirm:{channel_id}"),
        ],
    ])


def short_notification_keyboard(
    video_id: str,
    channel_id: str,
) -> InlineKeyboardMarkup:
    """Keyboard for shorts that are auto-sent."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ Favorite", callback_data=f"fav:add:{video_id}"),
            InlineKeyboardButton("⏭️ Skip", callback_data=f"skip:{video_id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Unsubscribe", callback_data=f"unsub:confirm:{channel_id}"),
        ],
    ])


def search_result_keyboard(
    video_id: str,
    channel_id: str,
) -> InlineKeyboardMarkup:
    """Keyboard for search results."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download", callback_data=f"dl:video:{video_id}"),
            InlineKeyboardButton("🎵 Audio", callback_data=f"dl:audio:{video_id}"),
        ],
        [
            InlineKeyboardButton("📋 Queue", callback_data=f"queue:add:{video_id}"),
            InlineKeyboardButton("🔔 Subscribe", callback_data=f"sub:quick:{channel_id}"),
        ],
    ])


def channel_list_keyboard(
    channels: List[Dict[str, Any]],
    page: int = 0,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    """Keyboard for channel list with pagination."""
    keyboard = []
    
    start = page * page_size
    end = start + page_size
    page_channels = channels[start:end]
    
    for channel in page_channels:
        priority_icon = "⭐ " if channel.get('is_priority') else ""
        name = channel.get('nickname') or channel.get('channel_name', 'Unknown')
        keyboard.append([
            InlineKeyboardButton(
                f"{priority_icon}{name}",
                callback_data=f"channel:view:{channel['channel_id']}"
            )
        ])
    
    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"channels:page:{page-1}"))
    if end < len(channels):
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"channels:page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Action row
    keyboard.append([
        InlineKeyboardButton("➕ Add Channel", callback_data="menu:subscribe"),
        InlineKeyboardButton("🔙 Back", callback_data="menu:main"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def channel_manage_keyboard(channel_id: str, is_priority: bool) -> InlineKeyboardMarkup:
    """Keyboard for managing a single channel."""
    priority_btn = (
        InlineKeyboardButton("⭐ Remove Priority", callback_data=f"priority:remove:{channel_id}")
        if is_priority else
        InlineKeyboardButton("⭐ Set Priority", callback_data=f"priority:set:{channel_id}")
    )
    
    return InlineKeyboardMarkup([
        [priority_btn],
        [InlineKeyboardButton("✏️ Set Nickname", callback_data=f"nickname:set:{channel_id}")],
        [InlineKeyboardButton("🗑️ Unsubscribe", callback_data=f"unsub:confirm:{channel_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="menu:list")],
    ])


def queue_keyboard(queue_items: List[Dict], page: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for queue management."""
    keyboard = []
    
    page_size = 5
    start = page * page_size
    end = start + page_size
    page_items = queue_items[start:end]
    
    for item in page_items:
        title = item.get('title', 'Unknown')[:30]
        keyboard.append([
            InlineKeyboardButton(f"📺 {title}", callback_data=f"queue:view:{item['video_id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"queue:remove:{item['video_id']}"),
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"queue:page:{page-1}"))
    if end < len(queue_items):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"queue:page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Actions
    if queue_items:
        keyboard.append([
            InlineKeyboardButton("📥 Download All", callback_data="queue:sync"),
            InlineKeyboardButton("🗑️ Clear All", callback_data="queue:clear"),
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    return InlineKeyboardMarkup(keyboard)


def settings_keyboard(settings: Dict) -> InlineKeyboardMarkup:
    """Settings menu keyboard."""
    keyboard = []
    
    # Daily limit
    limit = settings.get('daily_limit', 20)
    limit_text = "∞" if limit == 0 else str(limit)
    keyboard.append([
        InlineKeyboardButton(f"📊 Daily Limit: {limit_text}", callback_data="settings:limit")
    ])
    
    # Check interval
    interval = settings.get('check_interval', 15)
    keyboard.append([
        InlineKeyboardButton(f"⏱️ Check Interval: {interval}m", callback_data="settings:interval")
    ])
    
    # Resolution
    resolution = settings.get('resolution', '720')
    keyboard.append([
        InlineKeyboardButton(f"📺 Resolution: {resolution}p", callback_data="settings:resolution")
    ])
    
    # Quiet hours
    quiet_start = settings.get('quiet_start', '23:00')
    quiet_end = settings.get('quiet_end', '07:00')
    keyboard.append([
        InlineKeyboardButton(f"🌙 Quiet Hours: {quiet_start}-{quiet_end}", callback_data="settings:quiet")
    ])
    
    # Auto-download shorts
    auto_shorts = settings.get('auto_download_shorts', True)
    shorts_icon = "✅" if auto_shorts else "❌"
    keyboard.append([
        InlineKeyboardButton(f"🎬 Auto-send Shorts: {shorts_icon}", callback_data="settings:auto_shorts")
    ])
    
    # Timezone
    tz = settings.get('timezone', 'Asia/Kolkata')
    keyboard.append([
        InlineKeyboardButton(f"🕐 Timezone: {tz}", callback_data="settings:timezone")
    ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    return InlineKeyboardMarkup(keyboard)


def interval_keyboard(current: int) -> InlineKeyboardMarkup:
    """Check interval selector."""
    options = [5, 15, 30, 60]
    keyboard = []
    row = []
    
    for opt in options:
        text = f"{'✓ ' if opt == current else ''}{opt}m"
        row.append(InlineKeyboardButton(text, callback_data=f"settings:set_interval:{opt}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(keyboard)


def resolution_keyboard(current: str) -> InlineKeyboardMarkup:
    """Resolution selector."""
    options = ["360", "480", "720", "1080"]
    keyboard = []
    row = []
    
    for opt in options:
        text = f"{'✓ ' if opt == current else ''}{opt}p"
        row.append(InlineKeyboardButton(text, callback_data=f"settings:set_resolution:{opt}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(keyboard)


def limit_keyboard(current: int) -> InlineKeyboardMarkup:
    """Daily limit selector."""
    options = [10, 20, 50, 0]  # 0 = unlimited
    keyboard = []
    row = []
    
    for opt in options:
        text = "∞" if opt == 0 else str(opt)
        if opt == current:
            text = f"✓ {text}"
        row.append(InlineKeyboardButton(text, callback_data=f"settings:set_limit:{opt}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(keyboard)


def lofi_duration_keyboard() -> InlineKeyboardMarkup:
    """Lofi duration selector."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("30 min", callback_data="lofi:30"),
            InlineKeyboardButton("1 hour", callback_data="lofi:60"),
        ],
        [
            InlineKeyboardButton("2 hours", callback_data="lofi:120"),
            InlineKeyboardButton("3 hours", callback_data="lofi:180"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="menu:main")],
    ])


def favorites_keyboard(favorites: List[Dict], page: int = 0) -> InlineKeyboardMarkup:
    """Favorites list keyboard."""
    keyboard = []
    page_size = 5
    start = page * page_size
    end = start + page_size
    page_items = favorites[start:end]
    
    for item in page_items:
        title = item.get('title', 'Unknown')[:25]
        keyboard.append([
            InlineKeyboardButton(f"⭐ {title}", callback_data=f"fav:view:{item['video_id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"fav:remove:{item['video_id']}"),
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"fav:page:{page-1}"))
    if end < len(favorites):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"fav:page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:main")])
    
    return InlineKeyboardMarkup(keyboard)


def thumbnail_preview_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """Thumbnail preview with download options."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Download Video", callback_data=f"dl:video:{video_id}"),
            InlineKeyboardButton("🎵 Audio Only", callback_data=f"dl:audio:{video_id}"),
        ],
        [
            InlineKeyboardButton("📋 Add to Queue", callback_data=f"queue:add:{video_id}"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])


def duplicate_warning_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """Keyboard for duplicate video warning."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download Again", callback_data=f"dl:force:{video_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])
