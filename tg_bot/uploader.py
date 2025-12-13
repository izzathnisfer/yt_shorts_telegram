"""
Pyrogram-based file uploader for large files (up to 2GB).
Handles video and audio uploads with progress tracking.
"""

import os
import asyncio
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from pyrogram import Client
from pyrogram.errors import FloodWait
from tqdm import tqdm

from config import API_ID, API_HASH, BOT_TOKEN, MAX_FILE_SIZE_BYTES
from youtube.utils import format_file_size, format_duration

logger = logging.getLogger(__name__)

# Global Pyrogram client
_client: Optional[Client] = None
_client_lock = asyncio.Lock()


async def get_client() -> Client:
    """Get or create the Pyrogram client."""
    global _client
    
    async with _client_lock:
        if _client is None:
            _client = Client(
                "youtube_shorts_bot",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=BOT_TOKEN,
                workdir="."
            )
        
        if not _client.is_connected:
            await _client.start()
        
        return _client


async def stop_client():
    """Stop the Pyrogram client."""
    global _client
    
    async with _client_lock:
        if _client and _client.is_connected:
            await _client.stop()
            _client = None


def _get_readable_time(seconds: float) -> str:
    """Convert seconds to readable time string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def _human_bytes(size: int) -> str:
    """Convert bytes to human readable format."""
    return format_file_size(size)


async def _progress_callback(
    current: int,
    total: int,
    pbar: tqdm,
    start_time: float,
    action: str,
    last_update: list
):
    """Progress callback for Pyrogram uploads."""
    now = time.time()
    
    # Throttle updates to every 0.5 seconds
    if now - last_update[0] < 0.5 and current < total:
        return
    
    last_update[0] = now
    
    # Update progress bar
    pbar.n = current
    pbar.refresh()
    
    # Calculate speed and ETA
    elapsed = now - start_time
    if elapsed > 0 and current > 0:
        speed = current / elapsed
        remaining = total - current
        eta = remaining / speed if speed > 0 else 0
        
        pbar.set_postfix({
            'speed': f"{_human_bytes(int(speed))}/s",
            'eta': _get_readable_time(eta)
        })


async def upload_video(
    chat_id: int,
    file_path: str,
    caption: str = "",
    thumb: Optional[str] = None,
    duration: int = 0,
    width: int = 0,
    height: int = 0,
    reply_to_message_id: Optional[int] = None,
    reply_markup = None,
    progress_callback: Optional[Callable] = None,
) -> Optional[int]:
    """
    Upload a video file to Telegram using Pyrogram.
    
    Args:
        chat_id: Telegram chat ID to send to
        file_path: Path to the video file
        caption: Caption for the video
        thumb: Optional thumbnail path
        duration: Video duration in seconds
        width: Video width
        height: Video height
        reply_to_message_id: Optional message to reply to
        reply_markup: Optional inline keyboard
        progress_callback: Optional callback for progress updates
    
    Returns:
        Message ID of sent message or None on failure
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return None
    
    file_size = file_path.stat().st_size
    
    if file_size > MAX_FILE_SIZE_BYTES:
        logger.error(f"File too large: {_human_bytes(file_size)}")
        return None
    
    file_name = file_path.name
    logger.info(f"Starting upload of '{file_name}' ({_human_bytes(file_size)})")
    
    # Initialize progress bar
    pbar = tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
        desc=f"Uploading {file_name[:30]}..."
    )
    
    last_update = [0.0]
    start_time = time.time()
    
    try:
        client = await get_client()
        
        message = await client.send_video(
            chat_id=chat_id,
            video=str(file_path),
            caption=caption[:1024] if caption else "",  # Telegram caption limit
            thumb=thumb,
            duration=duration,
            width=width,
            height=height,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            supports_streaming=True,
            progress=_progress_callback,
            progress_args=(pbar, start_time, "Uploading", last_update)
        )
        
        pbar.n = file_size
        pbar.refresh()
        
        upload_duration = time.time() - start_time
        logger.info(f"Successfully uploaded '{file_name}' in {_get_readable_time(upload_duration)}")
        
        return message.id
        
    except FloodWait as e:
        logger.warning(f"FloodWait: Waiting {e.value} seconds before retrying")
        pbar.close()
        
        await asyncio.sleep(e.value + 1)
        
        # Retry once
        pbar = tqdm(
            total=file_size,
            unit="B",
            unit_scale=True,
            desc=f"Retrying {file_name[:30]}..."
        )
        last_update[0] = 0.0
        start_time = time.time()
        
        try:
            client = await get_client()
            
            message = await client.send_video(
                chat_id=chat_id,
                video=str(file_path),
                caption=caption[:1024] if caption else "",
                thumb=thumb,
                duration=duration,
                width=width,
                height=height,
                reply_to_message_id=reply_to_message_id,
                reply_markup=reply_markup,
                supports_streaming=True,
                progress=_progress_callback,
                progress_args=(pbar, start_time, "Uploading", last_update)
            )
            
            pbar.n = file_size
            pbar.refresh()
            
            return message.id
            
        except Exception as e:
            logger.error(f"Failed to upload after retry: {e}")
            return None
        finally:
            pbar.close()
            
    except Exception as e:
        logger.error(f"Failed to upload '{file_name}': {e}")
        return None
    finally:
        pbar.close()


async def upload_audio(
    chat_id: int,
    file_path: str,
    caption: str = "",
    title: str = "",
    performer: str = "",
    duration: int = 0,
    thumb: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    reply_markup = None,
) -> Optional[int]:
    """
    Upload an audio file to Telegram using Pyrogram.
    
    Returns:
        Message ID of sent message or None on failure
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return None
    
    file_size = file_path.stat().st_size
    file_name = file_path.name
    
    logger.info(f"Starting audio upload of '{file_name}' ({_human_bytes(file_size)})")
    
    pbar = tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
        desc=f"Uploading {file_name[:30]}..."
    )
    
    last_update = [0.0]
    start_time = time.time()
    
    try:
        client = await get_client()
        
        message = await client.send_audio(
            chat_id=chat_id,
            audio=str(file_path),
            caption=caption[:1024] if caption else "",
            title=title or file_path.stem,
            performer=performer,
            duration=duration,
            thumb=thumb,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            progress=_progress_callback,
            progress_args=(pbar, start_time, "Uploading", last_update)
        )
        
        pbar.n = file_size
        pbar.refresh()
        
        upload_duration = time.time() - start_time
        logger.info(f"Successfully uploaded audio '{file_name}' in {_get_readable_time(upload_duration)}")
        
        return message.id
        
    except FloodWait as e:
        logger.warning(f"FloodWait: Waiting {e.value} seconds")
        await asyncio.sleep(e.value + 1)
        
        # Retry once
        try:
            client = await get_client()
            message = await client.send_audio(
                chat_id=chat_id,
                audio=str(file_path),
                caption=caption[:1024] if caption else "",
                title=title or file_path.stem,
                performer=performer,
                duration=duration,
                thumb=thumb,
                reply_to_message_id=reply_to_message_id,
                reply_markup=reply_markup,
            )
            return message.id
        except Exception as e:
            logger.error(f"Failed to upload audio after retry: {e}")
            return None
        finally:
            pbar.close()
            
    except Exception as e:
        logger.error(f"Failed to upload audio '{file_name}': {e}")
        return None
    finally:
        pbar.close()


async def upload_document(
    chat_id: int,
    file_path: str,
    caption: str = "",
    file_name: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
) -> Optional[int]:
    """
    Upload a document file to Telegram with optional progress callback.
    
    Args:
        progress_callback: Optional async function(current, total) for progress updates
    
    Returns:
        Message ID of sent message or None on failure
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return None
    
    file_size = file_path.stat().st_size
    file_name_str = file_name or file_path.name
    
    logger.info(f"Starting document upload of '{file_name_str}' ({_human_bytes(file_size)})")
    
    pbar = tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
        desc=f"Uploading {file_name_str[:30]}..."
    )
    
    last_update = [0.0]
    start_time = time.time()
    
    async def _combined_progress(current: int, total: int):
        """Combined progress for tqdm and custom callback."""
        pbar.n = current
        pbar.refresh()
        
        # Call custom callback if provided (throttled)
        now = time.time()
        if progress_callback and now - last_update[0] >= 1.0:
            last_update[0] = now
            try:
                await progress_callback(current, total)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")
    
    try:
        client = await get_client()
        
        message = await client.send_document(
            chat_id=chat_id,
            document=str(file_path),
            caption=caption[:1024] if caption else "",
            file_name=file_name_str,
            reply_to_message_id=reply_to_message_id,
            force_document=True,
            progress=_combined_progress,
        )
        
        pbar.n = file_size
        pbar.refresh()
        
        upload_duration = time.time() - start_time
        logger.info(f"Successfully uploaded document '{file_name_str}' in {_get_readable_time(upload_duration)}")
        
        return message.id
        
    except FloodWait as e:
        logger.warning(f"FloodWait: Waiting {e.value} seconds")
        pbar.close()
        await asyncio.sleep(e.value + 1)
        
        try:
            client = await get_client()
            message = await client.send_document(
                chat_id=chat_id,
                document=str(file_path),
                caption=caption[:1024] if caption else "",
                file_name=file_name_str,
                reply_to_message_id=reply_to_message_id,
                force_document=True,
            )
            return message.id
        except Exception as e:
            logger.error(f"Failed to upload document after retry: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        return None
    finally:
        pbar.close()
