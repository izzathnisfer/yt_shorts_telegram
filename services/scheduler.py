"""
Background scheduler for periodic video checking and reports.
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from database import (
    get_all_active_users, get_subscriptions, get_user_settings,
    is_in_focus_mode, is_video_seen, mark_video_seen, get_today_watch_count
)
from youtube.info import get_channel_videos
from youtube.downloader import download_video, delete_file
from tg_bot.uploader import upload_video
from config import WEEKLY_REPORT_DAY, WEEKLY_REPORT_HOUR

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def check_new_videos_for_user(user_id: int, bot) -> None:
    """Check for new videos for a specific user."""
    try:
        # Check focus mode
        is_focus, _ = await is_in_focus_mode(user_id)
        if is_focus:
            logger.debug(f"User {user_id} in focus mode, skipping")
            return
        
        # Check quiet hours
        settings = await get_user_settings(user_id)
        if is_quiet_hours(settings):
            logger.debug(f"Quiet hours for user {user_id}, skipping non-priority")
            only_priority = True
        else:
            only_priority = False
        
        # Check daily limit
        limit = settings.get('daily_limit', 20)
        today_count = await get_today_watch_count(user_id)
        
        if limit > 0 and today_count >= limit:
            logger.debug(f"User {user_id} reached daily limit")
            return
        
        # Get subscriptions
        subscriptions = await get_subscriptions(user_id)
        
        for sub in subscriptions:
            # Skip non-priority during quiet hours
            if only_priority and not sub.get('is_priority'):
                continue
            
            try:
                # Get recent videos from channel
                videos = await get_channel_videos(sub['channel_url'], limit=5)
                
                for video in videos:
                    # Check if already seen
                    if await is_video_seen(user_id, video['id']):
                        continue
                    
                    # Mark as seen
                    await mark_video_seen(user_id, video['id'])
                    
                    # Check daily limit again
                    if limit > 0:
                        today_count = await get_today_watch_count(user_id)
                        if today_count >= limit:
                            break
                    
                    # Process video
                    await process_new_video(user_id, video, sub, settings, bot)
                    
                    # Break after first new video per channel to avoid spam
                    break
                    
            except Exception as e:
                logger.error(f"Error checking channel {sub['channel_name']}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error checking videos for user {user_id}: {e}")


async def process_new_video(user_id: int, video: dict, sub: dict, settings: dict, bot) -> None:
    """Process and send a new video notification."""
    from tg_bot.keyboards import video_notification_keyboard, short_notification_keyboard
    from database import add_to_history, record_watch
    
    channel_name = sub.get('nickname') or sub.get('channel_name')
    is_short = video.get('is_short', False)
    auto_download = settings.get('auto_download_shorts', True)
    
    if is_short and auto_download:
        # Auto-download and send shorts
        try:
            quality = settings.get('resolution', '720')
            file_path = await download_video(video['url'], quality=quality)
            
            if file_path:
                caption = (
                    f"🎬 **New Short from {channel_name}!**\n\n"
                    f"{video['title']}\n"
                    f"⏱️ {video['duration_string']}"
                )
                
                await upload_video(
                    chat_id=user_id,
                    file_path=file_path,
                    caption=caption,
                    duration=video.get('duration', 0),
                    reply_markup=short_notification_keyboard(video['id'], sub['channel_id'])
                )
                
                delete_file(file_path)
                
                # Record stats
                await add_to_history(
                    user_id=user_id,
                    video_id=video['id'],
                    title=video['title'],
                    channel_id=sub['channel_id'],
                    channel_name=sub['channel_name'],
                    duration=video.get('duration', 0),
                    is_short=True,
                    source='subscription'
                )
                
                await record_watch(
                    user_id=user_id,
                    channel_id=sub['channel_id'],
                    channel_name=sub['channel_name'],
                    duration=video.get('duration', 0),
                    is_short=True
                )
                
                return
        except Exception as e:
            logger.error(f"Error auto-downloading short: {e}")
    
    # Send notification for regular videos
    from youtube.utils import format_views
    
    message = (
        f"📺 **New from {channel_name}!**\n\n"
        f"🎬 {video['title']}\n"
        f"👁️ {format_views(video.get('view_count', 0))} views • ⏱️ {video['duration_string']}\n\n"
        f"🔗 {video['url']}"
    )
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=video_notification_keyboard(video['id'], sub['channel_id'])
        )
    except Exception as e:
        logger.error(f"Error sending notification to user {user_id}: {e}")


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
    """Run periodic check for all users."""
    logger.info("Running periodic video check...")
    
    users = await get_all_active_users()
    
    for user in users:
        await check_new_videos_for_user(user['user_id'], bot)
        await asyncio.sleep(1)  # Small delay between users


async def run_weekly_reports(bot) -> None:
    """Send weekly reports to all active users."""
    logger.info("Sending weekly reports...")
    
    users = await get_all_active_users()
    
    for user in users:
        await send_weekly_report(user['user_id'], bot)
        await asyncio.sleep(1)


def setup_scheduler(bot) -> AsyncIOScheduler:
    """Setup and start the background scheduler."""
    sched = get_scheduler()
    
    # Periodic video check (every 15 minutes)
    sched.add_job(
        run_periodic_check,
        trigger=IntervalTrigger(minutes=15),
        args=[bot],
        id='periodic_check',
        name='Check for new videos',
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
    
    logger.info("Scheduler started with periodic check and weekly reports")
    
    return sched


def stop_scheduler() -> None:
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler stopped")
