"""
AI Handler for Telegram messages.
Processes natural language messages and executes bot actions via AI.
"""

import logging
import re
from typing import Dict, Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

from services.ai_service import get_ai_service
from config import AI_ENABLED
from database import (
    get_user_settings, get_subscriptions, get_today_watch_count,
    is_in_focus_mode, get_queue, get_favorites, update_user_settings,
    get_daily_stats, get_weekly_stats, get_subscription,
    add_subscription, remove_subscription, set_channel_priority,
    set_channel_nickname, add_to_queue, remove_from_queue, clear_queue,
    add_favorite, remove_favorite, set_focus_mode
)

logger = logging.getLogger(__name__)


async def get_user_context(user_id: int, user) -> Dict[str, Any]:
    """Build user context for AI system prompt."""
    settings = await get_user_settings(user_id)
    subscriptions = await get_subscriptions(user_id)
    today_count = await get_today_watch_count(user_id)
    is_focus, focus_end = await is_in_focus_mode(user_id)
    
    return {
        "first_name": user.first_name if user else "User",
        "username": user.username if user else None,
        "subscription_count": len(subscriptions),
        "today_count": today_count,
        "daily_limit": settings.get('daily_limit', 20),
        "is_focus": is_focus,
        "focus_end": focus_end,
        "quality": settings.get('resolution', '720'),
    }


async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle non-command text messages with AI."""
    if not AI_ENABLED:
        return
    
    message = update.message
    if not message or not message.text:
        return
    
    user = update.effective_user
    user_id = user.id
    text = message.text.strip()
    
    # Skip if message looks like a command or URL-only
    if text.startswith('/'):
        return
    
    # Skip very short messages that might be accidents
    if len(text) < 3:
        return
    
    ai_service = get_ai_service()
    if not ai_service.is_available:
        return
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    
    # Get user context
    user_context = await get_user_context(user_id, user)
    
    # Determine if complex query needs smart model
    use_smart_model = _should_use_smart_model(text)
    
    # Process with AI
    result = await ai_service.process_message(
        user_id=user_id,
        message=text,
        user_context=user_context,
        use_smart_model=use_smart_model
    )
    
    if result.get("error"):
        if result["error"] == "rate_limited":
            await message.reply_text(result.get("response", "Please wait a moment."))
        else:
            logger.error(f"AI error: {result['error']}")
            # Silently fail - don't spam user with errors
        return
    
    # Handle tool calls
    if result.get("tool_calls"):
        tool_results = []
        
        for tool_call in result["tool_calls"]:
            tool_result = await _execute_tool(
                update=update,
                context=context,
                tool_name=tool_call["name"],
                arguments=tool_call["arguments"],
                user_id=user_id
            )
            tool_results.append({
                "name": tool_call["name"],
                "result": tool_result
            })
        
        # If we have results that need AI to format, get follow-up
        # Otherwise the tool execution already sent the response
        if not any(r.get("result", {}).get("message_sent") for r in tool_results):
            follow_up = await ai_service.get_follow_up_response(
                user_id=user_id,
                tool_results=tool_results,
                user_context=user_context
            )
            if follow_up:
                await message.reply_text(follow_up, parse_mode='Markdown')
    
    elif result.get("response"):
        # Direct text response
        await message.reply_text(result["response"], parse_mode='Markdown')


def _should_use_smart_model(text: str) -> bool:
    """Determine if the query needs the smarter (70B) model."""
    # Keywords that suggest complex analysis needed
    complex_keywords = [
        "analyze", "recommend", "suggest", "advice", "help me",
        "what should", "am i", "too much", "compare", "best",
        "explain", "why", "how much", "statistics", "pattern"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in complex_keywords)


async def _execute_tool(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """Execute an AI tool and return the result."""
    message = update.message
    
    try:
        # ============ YouTube Tools ============
        if tool_name == "search_youtube":
            from youtube.search import search_videos
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            results = await search_videos(query, limit=limit)
            
            if results:
                text = f"🔍 **Search results for '{query}':**\n\n"
                for i, video in enumerate(results[:5], 1):
                    text += f"{i}. **{video['title'][:50]}**\n"
                    text += f"   📺 {video['channel_name']} • ⏱️ {video['duration_string']}\n\n"
                
                await message.reply_text(text, parse_mode='Markdown')
                return {"success": True, "count": len(results), "message_sent": True}
            else:
                await message.reply_text("No results found. Try a different search term.")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "download_video":
            from youtube.downloader import download_video, delete_file
            from youtube.info import get_video_info
            from tg_bot.uploader import upload_video
            from youtube.utils import parse_time_range
            
            url = arguments.get("url", "")
            quality = arguments.get("quality", "720")
            
            status = await message.reply_text("⏳ Getting video info...")
            
            info = await get_video_info(url)
            if not info:
                await status.edit_text("❌ Could not get video info.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text(f"📥 Downloading: {info['title'][:50]}...")
            
            # Handle trimming
            trim_start = arguments.get("trim_start")
            trim_end = arguments.get("trim_end")
            
            if trim_start or trim_end:
                from youtube.downloader import download_video_trimmed
                start_sec = parse_time_range(trim_start) if trim_start else 0
                end_sec = parse_time_range(trim_end) if trim_end else info['duration']
                file_path = await download_video_trimmed(url, start_sec, end_sec, quality)
            else:
                file_path = await download_video(url, quality=quality)
            
            if not file_path:
                await status.edit_text("❌ Download failed.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text("📤 Uploading to Telegram...")
            
            caption = f"🎬 **{info['title']}**\n📺 {info['channel_name']}"
            msg_id = await upload_video(
                chat_id=user_id,
                file_path=file_path,
                caption=caption,
                duration=int(info['duration'])
            )
            
            delete_file(file_path)
            await status.delete()
            
            return {"success": True, "title": info['title'], "message_sent": True}
        
        elif tool_name == "download_audio":
            from youtube.downloader import download_audio, delete_file
            from youtube.info import get_video_info
            from tg_bot.uploader import upload_audio
            
            url = arguments.get("url", "")
            
            status = await message.reply_text("🎵 Extracting audio...")
            
            info = await get_video_info(url)
            if not info:
                await status.edit_text("❌ Could not get video info.")
                return {"success": False, "message_sent": True}
            
            file_path = await download_audio(url)
            if not file_path:
                await status.edit_text("❌ Audio extraction failed.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text("📤 Uploading audio...")
            
            caption = f"🎵 **{info['title']}**\n📺 {info['channel_name']}"
            await upload_audio(
                chat_id=user_id,
                file_path=file_path,
                caption=caption,
                title=info['title'],
                performer=info['channel_name'],
                duration=int(info['duration'])
            )
            
            delete_file(file_path)
            await status.delete()
            
            return {"success": True, "title": info['title'], "message_sent": True}
        
        elif tool_name == "get_video_info":
            from youtube.info import get_video_info
            
            url = arguments.get("url", "")
            info = await get_video_info(url)
            
            if info:
                text = f"📺 **{info['title']}**\n\n"
                text += f"👤 Channel: {info['channel_name']}\n"
                text += f"⏱️ Duration: {info['duration_string']}\n"
                text += f"👁️ Views: {info.get('view_count', 'N/A'):,}\n"
                
                await message.reply_text(text, parse_mode='Markdown')
                return {"success": True, "info": info, "message_sent": True}
            else:
                await message.reply_text("❌ Could not get video info.")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "get_lofi_music":
            from handlers.lofi import send_lofi
            
            duration = arguments.get("duration_minutes", 30)
            # Store duration and trigger lofi
            context.user_data['lofi_duration'] = duration
            await send_lofi(update, context, duration)
            return {"success": True, "duration": duration, "message_sent": True}
        
        # ============ Subscription Tools ============
        elif tool_name == "subscribe_channel":
            from youtube.info import get_channel_info
            
            channel = arguments.get("channel", "")
            
            status = await message.reply_text("🔍 Looking for channel...")
            
            info = await get_channel_info(channel)
            if not info:
                await status.edit_text("❌ Channel not found. Try the full channel URL.")
                return {"success": False, "message_sent": True}
            
            success = await add_subscription(
                user_id=user_id,
                channel_id=info['id'],
                channel_name=info['name'],
                channel_url=info['url']
            )
            
            if success:
                await status.edit_text(f"✅ Subscribed to **{info['name']}**!", parse_mode='Markdown')
            else:
                await status.edit_text(f"ℹ️ Already subscribed to {info['name']}")
            
            return {"success": success, "channel": info['name'], "message_sent": True}
        
        elif tool_name == "unsubscribe_channel":
            channel_name = arguments.get("channel_name", "")
            
            subscriptions = await get_subscriptions(user_id)
            match = None
            for sub in subscriptions:
                name = sub.get('nickname') or sub.get('channel_name', '')
                if channel_name.lower() in name.lower():
                    match = sub
                    break
            
            if match:
                await remove_subscription(user_id, match['channel_id'])
                await message.reply_text(f"✅ Unsubscribed from **{match['channel_name']}**", parse_mode='Markdown')
                return {"success": True, "channel": match['channel_name'], "message_sent": True}
            else:
                await message.reply_text(f"❌ Couldn't find channel matching '{channel_name}'")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "list_subscriptions":
            subscriptions = await get_subscriptions(user_id)
            
            if subscriptions:
                text = f"📋 **Your Subscriptions** ({len(subscriptions)})\n\n"
                for i, sub in enumerate(subscriptions[:15], 1):
                    priority = "⭐ " if sub.get('is_priority') else ""
                    name = sub.get('nickname') or sub.get('channel_name', 'Unknown')
                    text += f"{i}. {priority}{name}\n"
                
                if len(subscriptions) > 15:
                    text += f"\n_...and {len(subscriptions) - 15} more_"
                
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("📋 No subscriptions yet. Use /subscribe to add channels!")
            
            return {"success": True, "count": len(subscriptions), "message_sent": True}
        
        elif tool_name == "set_channel_priority":
            channel_name = arguments.get("channel_name", "")
            is_priority = arguments.get("is_priority", True)
            
            subscriptions = await get_subscriptions(user_id)
            match = None
            for sub in subscriptions:
                name = sub.get('nickname') or sub.get('channel_name', '')
                if channel_name.lower() in name.lower():
                    match = sub
                    break
            
            if match:
                await set_channel_priority(user_id, match['channel_id'], is_priority)
                status = "set as priority ⭐" if is_priority else "removed from priority"
                await message.reply_text(f"✅ **{match['channel_name']}** {status}", parse_mode='Markdown')
                return {"success": True, "message_sent": True}
            else:
                await message.reply_text(f"❌ Couldn't find channel matching '{channel_name}'")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "set_channel_nickname":
            channel_name = arguments.get("channel_name", "")
            nickname = arguments.get("nickname", "")
            
            subscriptions = await get_subscriptions(user_id)
            match = None
            for sub in subscriptions:
                name = sub.get('nickname') or sub.get('channel_name', '')
                if channel_name.lower() in name.lower():
                    match = sub
                    break
            
            if match:
                await set_channel_nickname(user_id, match['channel_id'], nickname or None)
                if nickname:
                    await message.reply_text(f"✅ Set nickname for {match['channel_name']} → **{nickname}**", parse_mode='Markdown')
                else:
                    await message.reply_text(f"✅ Removed nickname from {match['channel_name']}")
                return {"success": True, "message_sent": True}
            else:
                await message.reply_text(f"❌ Couldn't find channel matching '{channel_name}'")
                return {"success": False, "message_sent": True}
        
        # ============ Queue Tools ============
        elif tool_name == "get_queue":
            queue_items = await get_queue(user_id)
            
            if queue_items:
                from youtube.utils import format_duration
                total_duration = sum(item.get('duration', 0) for item in queue_items)
                
                text = f"📥 **Watch Queue** ({len(queue_items)} videos)\n"
                text += f"⏱️ Total: {format_duration(total_duration)}\n\n"
                
                for i, item in enumerate(queue_items[:10], 1):
                    text += f"{i}. {item['title'][:40]}...\n"
                
                if len(queue_items) > 10:
                    text += f"\n_...and {len(queue_items) - 10} more_"
                
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("📥 Your queue is empty!")
            
            return {"success": True, "count": len(queue_items), "message_sent": True}
        
        elif tool_name == "add_to_queue":
            from youtube.info import get_video_info
            
            url = arguments.get("video_url", "")
            info = await get_video_info(url)
            
            if info:
                success = await add_to_queue(
                    user_id=user_id,
                    video_id=info['id'],
                    video_url=info['webpage_url'],
                    title=info['title'],
                    channel_name=info['channel_name'],
                    duration=info['duration']
                )
                
                if success:
                    await message.reply_text(f"📋 Added to queue: **{info['title']}**", parse_mode='Markdown')
                else:
                    await message.reply_text("ℹ️ Already in your queue")
                return {"success": success, "message_sent": True}
            else:
                await message.reply_text("❌ Could not get video info")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "clear_queue":
            if not arguments.get("confirmed"):
                await message.reply_text("⚠️ Are you sure you want to clear your queue? Say 'yes, clear my queue'")
                return {"success": False, "needs_confirmation": True, "message_sent": True}
            
            count = await clear_queue(user_id)
            await message.reply_text(f"🗑️ Cleared {count} videos from your queue")
            return {"success": True, "cleared": count, "message_sent": True}
        
        elif tool_name == "sync_queue":
            from handlers.sync import start_sync
            await start_sync(update, context)
            return {"success": True, "message_sent": True}
        
        # ============ Favorites Tools ============
        elif tool_name == "get_favorites":
            favorites = await get_favorites(user_id)
            
            if favorites:
                text = f"⭐ **Favorites** ({len(favorites)})\n\n"
                for i, fav in enumerate(favorites[:10], 1):
                    text += f"{i}. {fav['title'][:40]}...\n"
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("⭐ No favorites yet!")
            
            return {"success": True, "count": len(favorites), "message_sent": True}
        
        # ============ Settings Tools ============
        elif tool_name == "get_settings":
            settings = await get_user_settings(user_id)
            is_focus, focus_end = await is_in_focus_mode(user_id)
            
            limit = settings.get('daily_limit', 20)
            limit_text = "Unlimited" if limit == 0 else str(limit)
            
            text = "⚙️ **Your Settings**\n\n"
            text += f"📺 Quality: {settings.get('resolution', '720')}p\n"
            text += f"📊 Daily limit: {limit_text}\n"
            text += f"⏱️ Check interval: {settings.get('check_interval', 15)} min\n"
            text += f"🌙 Quiet hours: {settings.get('quiet_start', '23:00')} - {settings.get('quiet_end', '07:00')}\n"
            text += f"🧘 Focus mode: {'Active' if is_focus else 'Inactive'}\n"
            
            await message.reply_text(text, parse_mode='Markdown')
            return {"success": True, "settings": settings, "message_sent": True}
        
        elif tool_name == "set_quality":
            quality = arguments.get("quality", "720")
            await update_user_settings(user_id, resolution=quality)
            await message.reply_text(f"✅ Video quality set to **{quality}p**", parse_mode='Markdown')
            return {"success": True, "message_sent": True}
        
        elif tool_name == "set_daily_limit":
            limit = arguments.get("limit", 20)
            await update_user_settings(user_id, daily_limit=limit)
            limit_text = "unlimited" if limit == 0 else str(limit)
            await message.reply_text(f"✅ Daily limit set to **{limit_text}**", parse_mode='Markdown')
            return {"success": True, "message_sent": True}
        
        elif tool_name == "set_quiet_hours":
            start = arguments.get("start_time", "23:00")
            end = arguments.get("end_time", "07:00")
            await update_user_settings(user_id, quiet_start=start, quiet_end=end)
            await message.reply_text(f"✅ Quiet hours set: {start} - {end}")
            return {"success": True, "message_sent": True}
        
        # ============ Focus Tools ============
        elif tool_name == "enable_focus":
            from youtube.utils import parse_duration_string
            from datetime import datetime, timedelta
            
            duration_str = arguments.get("duration", "1h")
            seconds = parse_duration_string(duration_str)
            
            if seconds:
                end_time = datetime.now() + timedelta(seconds=seconds)
                await set_focus_mode(user_id, end_time)
                
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                duration_text = f"{hours}h {minutes}m" if hours else f"{minutes}m"
                
                await message.reply_text(
                    f"🧘 **Focus Mode Enabled**\n\n"
                    f"Duration: {duration_text}\n"
                    f"🔕 Notifications paused\n\n"
                    f"_Focus on what matters!_",
                    parse_mode='Markdown'
                )
                return {"success": True, "message_sent": True}
            else:
                await message.reply_text("❌ Invalid duration. Try '30m', '1h', or '2h'")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "disable_focus":
            await set_focus_mode(user_id, None)
            await message.reply_text("✅ Focus mode disabled. Notifications resumed!")
            return {"success": True, "message_sent": True}
        
        elif tool_name == "get_focus_status":
            is_focus, focus_end = await is_in_focus_mode(user_id)
            
            if is_focus and focus_end:
                from datetime import datetime
                remaining = focus_end - datetime.now()
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes = remainder // 60
                remaining_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
                
                await message.reply_text(f"🧘 Focus mode is **active**\n⏱️ Remaining: {remaining_str}", parse_mode='Markdown')
            else:
                await message.reply_text("Focus mode is **inactive**", parse_mode='Markdown')
            
            return {"success": True, "is_focus": is_focus, "message_sent": True}
        
        # ============ Stats Tools ============
        elif tool_name == "get_stats":
            from handlers.stats import show_stats
            await show_stats(update, context)
            return {"success": True, "message_sent": True}
        
        elif tool_name == "get_today_stats":
            stats = await get_daily_stats(user_id)
            from youtube.utils import format_duration_long
            
            videos = stats['videos_watched'] + stats['shorts_watched']
            duration = format_duration_long(stats['total_duration'])
            
            text = f"📊 **Today's Stats**\n\n"
            text += f"📺 Videos: {stats['videos_watched']}\n"
            text += f"🎬 Shorts: {stats['shorts_watched']}\n"
            text += f"🎧 Lofi sessions: {stats['lofi_sessions']}\n"
            text += f"⏱️ Total time: {duration}\n"
            
            await message.reply_text(text, parse_mode='Markdown')
            return {"success": True, "stats": stats, "message_sent": True}
        
        elif tool_name == "get_top_channels":
            stats = await get_weekly_stats(user_id)
            top_channels = stats.get('top_channels', [])
            
            if top_channels:
                from youtube.utils import format_duration_long
                text = "🏆 **Top Channels (This Week)**\n\n"
                for i, ch in enumerate(top_channels[:5], 1):
                    duration = format_duration_long(ch['duration'])
                    text += f"{i}. {ch['channel_name']} ({duration})\n"
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("No watch data yet for this week!")
            
            return {"success": True, "channels": top_channels, "message_sent": True}
        
        # ============ Leech Tools ============
        elif tool_name == "leech_to_telegram":
            from handlers.leech import _run_leech_task
            
            url = arguments.get("url", "")
            # Trigger leech download
            context.args = [url]
            await _run_leech_task(update, context, url, upload_target="telegram")
            return {"success": True, "message_sent": True}
        
        elif tool_name == "leech_to_nextcloud":
            from handlers.leech import _run_leech_task
            
            url = arguments.get("url", "")
            context.args = [url]
            await _run_leech_task(update, context, url, upload_target="nextcloud")
            return {"success": True, "message_sent": True}
        
        # ============ Utility Tools ============
        elif tool_name == "get_help":
            from handlers.help import show_help
            await show_help(update, context)
            return {"success": True, "message_sent": True}
        
        elif tool_name == "send_message":
            # Direct message from AI
            msg = arguments.get("message", "")
            await message.reply_text(msg, parse_mode='Markdown')
            return {"success": True, "message_sent": True}
        
        else:
            logger.warning(f"Unknown tool: {tool_name}")
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    except Exception as e:
        logger.error(f"Tool execution error ({tool_name}): {e}")
        return {"success": False, "error": str(e)}
