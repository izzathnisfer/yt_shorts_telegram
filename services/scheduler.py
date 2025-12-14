"""
Background scheduler for periodic video checking and reports.
Implements efficient batch channel checking with notification tracking.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from database import (
    get_all_active_users, get_subscriptions, get_user_settings,
    is_in_focus_mode, get_today_watch_count,
    # Optimized batch functions
    get_channels_with_subscribers, add_channel_videos_bulk, log_notifications_bulk,
    get_due_snoozes, mark_snooze_reminded,
    # Cached functions
    get_user_settings_cached, get_admin_setting_cached
)
from youtube.info import get_channel_videos
from youtube.downloader import download_video, delete_file
from tg_bot.uploader import upload_video
from config import WEEKLY_REPORT_DAY, WEEKLY_REPORT_HOUR

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def escape_markdown(text: str) -> str:
    """Escape markdown special characters in text."""
    if not text:
        return text
    # Escape characters that have special meaning in Telegram Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def check_all_channels(bot) -> None:
    """
    OPTIMIZED batch check: uses single queries instead of per-video calls.
    Reduces DB compute from ~2500 queries to ~10-20 per check cycle.
    """
    logger.info("Running batch channel video check...")
    
    # OPTIMIZATION 1: Single query gets all channels WITH their subscribers
    channels = await get_channels_with_subscribers()
    
    new_videos_count = 0
    notifications_sent = 0
    notifications_to_log = []  # Batch collect for bulk insert
    
    for channel in channels:
        try:
            # Get recent videos from channel (YouTube API call, not DB)
            videos = await get_channel_videos(channel['channel_url'], limit=50)
            
            if not videos:
                continue
            
            subscribers = channel['subscribers']  # Already have from single query
            video_ids = [v['id'] for v in videos]
            
            # Batch add videos to channel_videos table
            videos_to_add = [
                (channel['channel_id'], v['id'], v['title'], 
                 v.get('duration', 0), v.get('is_short', False), v.get('upload_date'))
                for v in videos
            ]
            new_video_ids = await add_channel_videos_bulk(videos_to_add)
            
            if not new_video_ids:
                continue  # No new videos for this channel
            
            new_videos_count += len(new_video_ids)
            
            # Filter to only new videos
            new_videos = [v for v in videos if v['id'] in new_video_ids]
            
            for video in new_videos:
                logger.info(f"New video detected: {video['title'][:50]}...")
                video_upload_date = video.get('upload_date')
                
                # OPTIMIZATION 2: Batch check notifications per subscriber
                for sub in subscribers:
                    user_id = sub['user_id']
                    subscribed_at = sub.get('subscribed_at')
                    
                    # Check upload date vs subscription date (no DB call)
                    if video_upload_date and subscribed_at:
                        if video_upload_date < subscribed_at:
                            # Video is older than subscription - mark as pre_subscription
                            notifications_to_log.append((user_id, video['id'], channel['channel_id'], 'pre_subscription'))
                            continue
                    
                    # Check user settings (uses cached version)
                    if not await should_notify_user(user_id, sub):
                        continue
                    
                    try:
                        # Send notification
                        await send_video_notification(
                            bot=bot,
                            user_id=user_id,
                            video=video,
                            channel_name=sub.get('nickname') or channel['channel_name'],
                            is_priority=sub.get('is_priority', False)
                        )
                        
                        # Collect for batch insert
                        notification_type = 'short' if video.get('is_short') else 'video'
                        notifications_to_log.append((user_id, video['id'], channel['channel_id'], notification_type))
                        notifications_sent += 1
                        
                    except Exception as e:
                        logger.error(f"Error notifying user {user_id}: {e}")
                        continue
                
                # Small delay between processing videos
                await asyncio.sleep(0.1)
            
            # Small delay between channels
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error checking channel {channel['channel_name']}: {e}")
            continue
    
    # OPTIMIZATION 3: Batch insert all notifications at once
    if notifications_to_log:
        await log_notifications_bulk(notifications_to_log)
        logger.info(f"Logged {len(notifications_to_log)} notifications in single batch")
    
    logger.info(f"Batch check complete: {new_videos_count} new videos, {notifications_sent} notifications sent")


async def should_notify_user(user_id: int, subscription: dict) -> bool:
    """Check if user should receive notification."""
    try:
        # Check focus mode
        is_focus, _ = await is_in_focus_mode(user_id)
        if is_focus:
            return False
        
        # Check quiet hours (using cached settings)
        settings = await get_user_settings_cached(user_id)
        if is_quiet_hours(settings) and not subscription.get('is_priority'):
            return False
        
        # Check daily limit
        limit = settings.get('daily_limit', 20)
        if limit > 0:
            today_count = await get_today_watch_count(user_id)
            if today_count >= limit:
                return False
        
        return True
    except Exception as e:
        logger.error(f"Error checking notify settings for user {user_id}: {e}")
        return True  # Default to notify


async def send_video_notification(bot, user_id: int, video: dict, 
                                   channel_name: str, is_priority: bool = False) -> None:
    """Send notification for a new video."""
    from tg_bot.keyboards import video_notification_keyboard, short_notification_keyboard
    from database import add_to_history, record_watch, get_user_settings
    from youtube.utils import format_views
    
    is_short = video.get('is_short', False)
    settings = await get_user_settings(user_id)
    auto_download = settings.get('auto_download_shorts', True)
    
    priority_icon = "⭐ " if is_priority else ""
    
    if is_short and auto_download:
        # Auto-download and send shorts
        try:
            quality = settings.get('resolution', '720')
            file_path = await download_video(video['url'], quality=quality)
            
            if file_path:
                caption = (
                    f"{priority_icon}🎬 **New Short from {channel_name}!**\n\n"
                    f"{video['title']}\n"
                    f"⏱️ {video.get('duration_string', '')}"
                )
                
                await upload_video(
                    chat_id=user_id,
                    file_path=file_path,
                    caption=caption,
                    duration=video.get('duration', 0),
                    reply_markup=short_notification_keyboard(video['id'], video.get('channel_id', ''))
                )
                
                delete_file(file_path)
                
                # Record stats
                await add_to_history(
                    user_id=user_id,
                    video_id=video['id'],
                    title=video['title'],
                    channel_id=video.get('channel_id', ''),
                    channel_name=channel_name,
                    duration=video.get('duration', 0),
                    is_short=True,
                    source='subscription'
                )
                
                await record_watch(
                    user_id=user_id,
                    channel_id=video.get('channel_id', ''),
                    channel_name=channel_name,
                    duration=video.get('duration', 0),
                    is_short=True
                )
                
                return
        except Exception as e:
            logger.error(f"Error auto-downloading short: {e}")
    
    # Escape markdown special characters in title
    safe_title = escape_markdown(video['title'])
    safe_channel = escape_markdown(channel_name)
    
    # Send notification message
    message = (
        f"{priority_icon}📺 **New from {safe_channel}!**\n\n"
        f"🎬 {safe_title}\n"
        f"👁️ {format_views(video.get('view_count', 0))} views • ⏱️ {video.get('duration_string', '')}\n\n"
        f"🔗 {video.get('url', '')}"
    )
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=video_notification_keyboard(video['id'], video.get('channel_id', ''))
        )
    except Exception as e:
        logger.error(f"Error sending notification to user {user_id}: {e}")


async def process_snooze_reminders(bot) -> None:
    """Process snoozed notifications that are due."""
    logger.info("Processing snooze reminders...")
    
    due_snoozes = await get_due_snoozes()
    
    for snooze in due_snoozes:
        try:
            user_id = snooze['user_id']
            
            # Check if user should be notified
            if not await should_notify_user(user_id, {}):
                continue
            
            # Send reminder
            message = (
                f"⏰ **Reminder: Watch Later**\n\n"
                f"🎬 {snooze['video_title']}\n\n"
                f"You snoozed this video earlier. Ready to watch?"
            )
            
            from tg_bot.keyboards import snooze_reminder_keyboard
            
            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=snooze_reminder_keyboard(snooze['video_id'], snooze['channel_id'])
            )
            
            # Mark as reminded
            await mark_snooze_reminded(snooze['id'])
            
        except Exception as e:
            logger.error(f"Error processing snooze reminder: {e}")
            continue
    
    if due_snoozes:
        logger.info(f"Processed {len(due_snoozes)} snooze reminders")


def is_quiet_hours(settings: dict) -> bool:
    """Check if current time is in quiet hours."""
    quiet_start = settings.get('quiet_start')
    quiet_end = settings.get('quiet_end')
    
    if not quiet_start or not quiet_end:
        return False
    
    try:
        now = datetime.now().time()
        start = datetime.strptime(quiet_start, '%H:%M').time()
        end = datetime.strptime(quiet_end, '%H:%M').time()
        
        if start <= end:
            return start <= now <= end
        else:
            # Overnight quiet hours (e.g., 23:00 - 07:00)
            return now >= start or now <= end
    except:
        return False


async def send_weekly_report(user_id: int, bot) -> None:
    """Send weekly statistics report."""
    from database import get_weekly_stats
    from youtube.utils import format_duration_long
    
    try:
        stats = await get_weekly_stats(user_id)
        
        weekly_videos = stats['videos_watched'] + stats['shorts_watched']
        weekly_duration = format_duration_long(stats['total_duration'])
        weekly_lofi = format_duration_long(stats['lofi_duration'])
        
        # Estimate time saved
        estimated_saved = (weekly_videos // 5) * 30  # minutes
        saved_str = format_duration_long(estimated_saved * 60)
        
        message = f"""
📊 **Weekly Report**

**This Week:**
├ 📺 {weekly_videos} videos watched
├ 🎬 {stats['shorts_watched']} shorts
├ 🎧 {weekly_lofi} of lofi music
├ ⏱️ {weekly_duration} total
└ 💪 ~{saved_str} saved vs YouTube scrolling!

"""
        
        if stats.get('top_channels'):
            message += "**Top Channels (by time spent):**\n"
            for i, ch in enumerate(stats['top_channels'][:5], 1):
                duration = format_duration_long(ch['duration'])
                message += f"{i}. {ch['channel_name']} - {ch['videos']} videos ({duration})\n"
        
        message += "\n🎯 Keep it intentional!"
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error sending weekly report to user {user_id}: {e}")


async def run_periodic_check(bot) -> None:
    """Run the main periodic check."""
    await check_all_channels(bot)


async def run_snooze_check(bot) -> None:
    """Run snooze reminder check."""
    await process_snooze_reminders(bot)


async def run_weekly_reports(bot) -> None:
    """Send weekly reports to all active users."""
    logger.info("Sending weekly reports...")
    
    users = await get_all_active_users()
    
    for user in users:
        await send_weekly_report(user['user_id'], bot)
        await asyncio.sleep(1)


async def setup_scheduler(bot) -> AsyncIOScheduler:
    """Setup and start the background scheduler."""
    sched = get_scheduler()
    
    # Get check interval from admin settings (cached, 5 min TTL)
    interval_str = await get_admin_setting_cached('check_interval_minutes', '15')
    check_interval = int(interval_str)
    
    # Periodic video check
    sched.add_job(
        run_periodic_check,
        trigger=IntervalTrigger(minutes=check_interval),
        args=[bot],
        id='periodic_check',
        name='Check for new videos',
        replace_existing=True
    )
    
    # Snooze reminder check (every 5 minutes)
    sched.add_job(
        run_snooze_check,
        trigger=IntervalTrigger(minutes=5),
        args=[bot],
        id='snooze_check',
        name='Process snooze reminders',
        replace_existing=True
    )
    
    # Weekly report (Sundays at 10 AM)
    sched.add_job(
        run_weekly_reports,
        trigger=CronTrigger(
            day_of_week=WEEKLY_REPORT_DAY,
            hour=WEEKLY_REPORT_HOUR,
            minute=0
        ),
        args=[bot],
        id='weekly_report',
        name='Send weekly reports',
        replace_existing=True
    )
    
    if not sched.running:
        sched.start()
    
    logger.info(f"Scheduler started: check every {check_interval} mins, snooze check every 5 mins")
    
    return sched


def stop_scheduler() -> None:
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler stopped")
