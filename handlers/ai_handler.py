"""
AI Handler for Telegram messages.
Executes AI tool calls and sends responses.
"""

import json
import logging
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from services.ai_service import get_ai_service
from config import AI_ENABLED
from database import (
    get_user_settings, get_subscriptions, get_today_watch_count,
    is_in_focus_mode, get_queue, add_subscription, set_focus_mode
)

logger = logging.getLogger(__name__)


async def get_user_context(user_id: int, user) -> Dict[str, Any]:
    """Build user context for AI."""
    settings = await get_user_settings(user_id)
    subscriptions = await get_subscriptions(user_id)
    today_count = await get_today_watch_count(user_id)
    is_focus, _ = await is_in_focus_mode(user_id)
    
    return {
        "first_name": user.first_name if user else "User",
        "subscription_count": len(subscriptions),
        "today_count": today_count,
        "daily_limit": settings.get('daily_limit', 20),
        "is_focus": is_focus,
    }


async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages with AI."""
    if not AI_ENABLED:
        return
    
    message = update.message
    if not message or not message.text:
        return
    
    user = update.effective_user
    user_id = user.id
    text = message.text.strip()
    
    # Skip commands and very short messages
    if text.startswith('/') or len(text) < 2:
        return
    
    ai_service = get_ai_service()
    if not ai_service.is_available:
        return
    
    # Show typing
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    
    user_context = await get_user_context(user_id, user)
    
    # Process with AI
    result = await ai_service.process_message(
        user_id=user_id,
        message=text,
        user_context=user_context
    )
    
    if result.get("error"):
        if result["error"] == "rate_limited":
            await message.reply_text(result.get("response", "⏳ Please wait..."))
        else:
            logger.error(f"AI error: {result['error']}")
        return
    
    # Handle tool calls
    if result.get("tool_calls"):
        for tool_call in result["tool_calls"]:
            tool_result = await execute_tool(
                update=update,
                context=context,
                tool_name=tool_call["name"],
                arguments=tool_call["arguments"],
                user_id=user_id
            )
            
            # Send result back to AI for nice response (if not already handled)
            if not tool_result.get("message_sent"):
                final_response = await ai_service.send_tool_result(
                    user_id=user_id,
                    tool_call_id=tool_call["id"],
                    tool_name=tool_call["name"],
                    result=json.dumps(tool_result),
                    user_context=user_context
                )
                if final_response:
                    try:
                        await message.reply_text(final_response, parse_mode='Markdown')
                    except:
                        await message.reply_text(final_response)
    
    elif result.get("response"):
        # Regular chat response
        try:
            await message.reply_text(result["response"], parse_mode='Markdown')
        except:
            await message.reply_text(result["response"])


async def execute_tool(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """Execute a tool and return result."""
    message = update.message
    
    try:
        # ============ YouTube Tools ============
        if tool_name == "search_youtube":
            from youtube.search import search_videos
            query = arguments.get("query", "")
            results = await search_videos(query, limit=5)
            
            if results:
                text = f"🔍 **Results for '{query}':**\n\n"
                for i, v in enumerate(results[:5], 1):
                    title = v.get('title', 'Unknown')[:45]
                    channel = v.get('channel_name', 'Unknown')
                    duration = v.get('duration_string', '')
                    text += f"{i}. **{title}**\n   📺 {channel} • ⏱️ {duration}\n\n"
                
                await message.reply_text(text, parse_mode='Markdown')
                return {"success": True, "count": len(results), "message_sent": True}
            else:
                await message.reply_text(f"No results for '{query}'. Try different keywords!")
                return {"success": False, "message_sent": True}
        
        elif tool_name == "download_video":
            from youtube.downloader import download_video as dl_video, delete_file
            from youtube.info import get_video_info
            
            url = arguments.get("url", "")
            status = await message.reply_text("⏳ Getting video info...")
            
            info = await get_video_info(url)
            if not info:
                await status.edit_text("❌ Could not get video info. Check the URL.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text(f"📥 Downloading: {info['title'][:40]}...")
            
            file_path = await dl_video(url, quality="720")
            if not file_path:
                await status.edit_text("❌ Download failed.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text("📤 Uploading...")
            
            from tg_bot.uploader import upload_video
            caption = f"🎬 **{info['title']}**\n📺 {info.get('channel_name', '')}"
            await upload_video(
                context.bot, user_id, file_path,
                caption=caption,
                duration=int(info.get('duration', 0))
            )
            
            delete_file(file_path)
            await status.delete()
            return {"success": True, "title": info['title'], "message_sent": True}
        
        elif tool_name == "download_audio":
            from youtube.downloader import download_audio as dl_audio, delete_file
            from youtube.info import get_video_info
            
            url = arguments.get("url", "")
            status = await message.reply_text("🎵 Extracting audio...")
            
            info = await get_video_info(url)
            if not info:
                await status.edit_text("❌ Could not get video info.")
                return {"success": False, "message_sent": True}
            
            file_path = await dl_audio(url)
            if not file_path:
                await status.edit_text("❌ Audio extraction failed.")
                return {"success": False, "message_sent": True}
            
            await status.edit_text("📤 Uploading audio...")
            
            from tg_bot.uploader import upload_audio
            await upload_audio(
                context.bot, user_id, file_path,
                title=info['title'],
                performer=info.get('channel_name', ''),
                duration=int(info.get('duration', 0))
            )
            
            delete_file(file_path)
            await status.delete()
            return {"success": True, "title": info['title'], "message_sent": True}
        
        # ============ Subscription Tools ============
        elif tool_name == "list_subscriptions":
            subs = await get_subscriptions(user_id)
            
            if subs:
                text = f"📋 **Your Subscriptions** ({len(subs)})\n\n"
                for i, s in enumerate(subs[:10], 1):
                    name = s.get('nickname') or s.get('channel_name', 'Unknown')
                    priority = "⭐ " if s.get('is_priority') else ""
                    text += f"{i}. {priority}{name}\n"
                
                if len(subs) > 10:
                    text += f"\n...and {len(subs) - 10} more"
                
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("📋 No subscriptions yet! Use /subscribe to add channels.")
            
            return {"success": True, "count": len(subs), "message_sent": True}
        
        elif tool_name == "subscribe_channel":
            from youtube.info import get_channel_info
            
            channel = arguments.get("channel", "")
            status = await message.reply_text("🔍 Finding channel...")
            
            info = await get_channel_info(channel)
            if not info:
                await status.edit_text("❌ Channel not found. Try the full URL.")
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
                await status.edit_text(f"Already subscribed to {info['name']}")
            
            return {"success": success, "channel": info['name'], "message_sent": True}
        
        # ============ Productivity Tools ============
        elif tool_name == "enable_focus":
            from datetime import datetime, timedelta
            
            duration_str = arguments.get("duration", "30m")
            
            # Parse duration
            minutes = 30
            if 'h' in duration_str:
                hours = int(duration_str.replace('h', '').strip())
                minutes = hours * 60
            elif 'm' in duration_str:
                minutes = int(duration_str.replace('m', '').strip())
            
            end_time = datetime.now() + timedelta(minutes=minutes)
            await set_focus_mode(user_id, end_time)
            
            await message.reply_text(
                f"🧘 **Focus Mode Enabled**\n\n"
                f"Duration: {minutes} minutes\n"
                f"🔕 Notifications paused\n\n"
                f"_Focus on what matters!_",
                parse_mode='Markdown'
            )
            return {"success": True, "duration": minutes, "message_sent": True}
        
        elif tool_name == "disable_focus":
            await set_focus_mode(user_id, None)
            await message.reply_text("✅ Focus mode disabled. Notifications resumed!")
            return {"success": True, "message_sent": True}
        
        elif tool_name == "get_lofi_music":
            from handlers.lofi import send_lofi
            
            duration = arguments.get("duration_minutes", 30)
            await send_lofi(update, context, duration)
            return {"success": True, "duration": duration, "message_sent": True}
        
        # ============ Info Tools ============
        elif tool_name == "get_stats":
            from handlers.stats import show_stats
            await show_stats(update, context)
            return {"success": True, "message_sent": True}
        
        elif tool_name == "get_settings":
            settings = await get_user_settings(user_id)
            is_focus, _ = await is_in_focus_mode(user_id)
            
            limit = settings.get('daily_limit', 20)
            limit_text = "Unlimited" if limit == 0 else str(limit)
            
            text = "⚙️ **Settings**\n\n"
            text += f"📺 Quality: {settings.get('resolution', '720')}p\n"
            text += f"📊 Daily limit: {limit_text}\n"
            text += f"🧘 Focus: {'Active' if is_focus else 'Off'}\n"
            
            await message.reply_text(text, parse_mode='Markdown')
            return {"success": True, "message_sent": True}
        
        elif tool_name == "get_queue":
            queue_items = await get_queue(user_id)
            
            if queue_items:
                text = f"📥 **Queue** ({len(queue_items)} videos)\n\n"
                for i, item in enumerate(queue_items[:8], 1):
                    text += f"{i}. {item.get('title', 'Unknown')[:35]}...\n"
                
                if len(queue_items) > 8:
                    text += f"\n...and {len(queue_items) - 8} more"
                
                await message.reply_text(text, parse_mode='Markdown')
            else:
                await message.reply_text("📥 Queue is empty!")
            
            return {"success": True, "count": len(queue_items), "message_sent": True}
        
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    except Exception as e:
        logger.error(f"Tool error ({tool_name}): {e}")
        return {"success": False, "error": str(e)}
