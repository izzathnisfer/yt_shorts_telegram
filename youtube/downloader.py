"""
YouTube video downloader using yt-dlp.
Supports video, audio, and trimmed downloads.
Memory-efficient streaming to disk.
"""

import yt_dlp
import os
import asyncio
from pathlib import Path
from typing import Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor
import logging
import subprocess
import shutil

from config import DOWNLOADS_PATH, YTDLP_FORMAT, YTDLP_AUDIO_FORMAT, MAX_FILE_SIZE_BYTES, COOKIES_PATH
from .utils import sanitize_filename, parse_time_range

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


class DownloadProgress:
    """Track download progress for callbacks."""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.speed = 0
        self.eta = 0
        self.status = "starting"
    
    def hook(self, d: dict):
        """Progress hook for yt-dlp."""
        if d['status'] == 'downloading':
            self.status = "downloading"
            self.total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            self.downloaded_bytes = d.get('downloaded_bytes', 0)
            self.speed = d.get('speed', 0)
            self.eta = d.get('eta', 0)
            
            if self.callback and self.total_bytes:
                progress = self.downloaded_bytes / self.total_bytes
                asyncio.create_task(self.callback(progress, self.speed, self.eta))
        
        elif d['status'] == 'finished':
            self.status = "finished"
            if self.callback:
                asyncio.create_task(self.callback(1.0, 0, 0))


def _download_video_sync(
    url: str,
    output_path: str,
    quality: str = "720",
    progress_hook: Optional[Callable] = None
) -> Optional[str]:
    """
    Synchronous video download (runs in thread pool).
    Returns the path to downloaded file or None on failure.
    """
    try:
        ydl_opts = {
            'format': YTDLP_FORMAT.replace('%(quality)s', quality),
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }
        
        # Add cookies if file exists
        if COOKIES_PATH.exists():
            ydl_opts['cookiefile'] = str(COOKIES_PATH)
        
        if progress_hook:
            ydl_opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find the actual output file (might have different extension)
        base_path = Path(output_path).with_suffix('')
        for ext in ['.mp4', '.mkv', '.webm']:
            check_path = base_path.with_suffix(ext)
            if check_path.exists():
                # Rename to .mp4 if needed
                if ext != '.mp4':
                    final_path = base_path.with_suffix('.mp4')
                    shutil.move(str(check_path), str(final_path))
                    return str(final_path)
                return str(check_path)
        
        return None
        
    except Exception as e:
        logger.error(f"Download error for {url}: {e}")
        return None


def _download_audio_sync(
    url: str,
    output_path: str,
    progress_hook: Optional[Callable] = None
) -> Optional[str]:
    """
    Synchronous audio download (runs in thread pool).
    Returns the path to downloaded MP3 file or None on failure.
    """
    try:
        ydl_opts = {
            'format': YTDLP_AUDIO_FORMAT,
            'outtmpl': output_path,
            'quiet': False,  # Show output for debugging
            'no_warnings': False,
            'ignoreerrors': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        # Add cookies if file exists
        if COOKIES_PATH.exists():
            ydl_opts['cookiefile'] = str(COOKIES_PATH)
        
        if progress_hook:
            ydl_opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find the MP3 file - yt-dlp adds .mp3 extension via postprocessor
        base_path = Path(output_path)
        mp3_path = Path(str(output_path) + '.mp3')
        
        logger.debug(f"Looking for audio file at: {mp3_path}")
        
        if mp3_path.exists():
            logger.info(f"Found audio file: {mp3_path}")
            return str(mp3_path)
        
        # Try with suffix method
        mp3_path_alt = base_path.with_suffix('.mp3')
        if mp3_path_alt.exists():
            logger.info(f"Found audio file (alt): {mp3_path_alt}")
            return str(mp3_path_alt)
        
        # Fallback: glob for any matching mp3 files in downloads directory
        downloads_dir = base_path.parent
        filename_start = base_path.name[:30]  # First 30 chars for matching
        
        for mp3_file in downloads_dir.glob('*.mp3'):
            if mp3_file.name.startswith(filename_start):
                logger.info(f"Found audio file via glob: {mp3_file}")
                return str(mp3_file)
        
        # Check for other audio formats and convert
        for ext in ['.m4a', '.webm', '.opus']:
            check_path = Path(str(output_path) + ext)
            if check_path.exists():
                # Convert to MP3
                try:
                    mp3_output = Path(str(output_path) + '.mp3')
                    subprocess.run([
                        'ffmpeg', '-y', '-i', str(check_path),
                        '-vn', '-acodec', 'libmp3lame', '-q:a', '2',
                        str(mp3_output)
                    ], check=True, capture_output=True)
                    check_path.unlink()  # Remove original
                    return str(mp3_output)
                except Exception as e:
                    logger.error(f"FFmpeg conversion error: {e}")
                    return str(check_path)  # Return original format
        
        # Last resort - list all files in downloads
        logger.warning(f"Could not find audio file. Downloads dir contents: {list(downloads_dir.glob('*'))[:5]}")
        
        return None
        
    except Exception as e:
        logger.error(f"Audio download error for {url}: {e}")
        return None


async def download_video(
    url: str,
    quality: str = "720",
    filename: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Download a video from YouTube.
    
    Args:
        url: YouTube video URL
        quality: Video quality (360, 480, 720, 1080)
        filename: Optional custom filename (without extension)
        progress_callback: Optional async callback(progress, speed, eta)
    
    Returns:
        Path to downloaded file or None on failure
    """
    loop = asyncio.get_event_loop()
    
    # Generate output path
    if not filename:
        from .info import get_video_info
        info = await get_video_info(url)
        if info:
            filename = sanitize_filename(info.get('title', 'video'))
        else:
            filename = "video"
    
    output_path = str(DOWNLOADS_PATH / f"{filename}.mp4")
    
    # Setup progress tracking
    progress = DownloadProgress(progress_callback)
    
    # Run download in thread pool
    result = await loop.run_in_executor(
        _executor,
        lambda: _download_video_sync(url, output_path, quality, progress.hook)
    )
    
    return result


async def download_audio(
    url: str,
    filename: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Download audio only from YouTube video.
    
    Args:
        url: YouTube video URL
        filename: Optional custom filename (without extension)
        progress_callback: Optional async callback(progress, speed, eta)
    
    Returns:
        Path to downloaded MP3 file or None on failure
    """
    loop = asyncio.get_event_loop()
    
    # Generate output path
    if not filename:
        from .info import get_video_info
        info = await get_video_info(url)
        if info:
            filename = sanitize_filename(info.get('title', 'audio'))
        else:
            filename = "audio"
    
    # Don't add .mp3 here - yt-dlp postprocessor will add it
    output_path = str(DOWNLOADS_PATH / filename)
    
    # Setup progress tracking
    progress = DownloadProgress(progress_callback)
    
    # Run download in thread pool
    result = await loop.run_in_executor(
        _executor,
        lambda: _download_audio_sync(url, output_path, progress.hook)
    )
    
    return result


async def download_video_trimmed(
    url: str,
    start_time: int,
    end_time: int,
    quality: str = "720",
    filename: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Download a trimmed portion of a YouTube video.
    
    Args:
        url: YouTube video URL
        start_time: Start time in seconds
        end_time: End time in seconds
        quality: Video quality
        filename: Optional custom filename
        progress_callback: Optional progress callback
    
    Returns:
        Path to trimmed video file or None on failure
    """
    # First download the full video
    if not filename:
        from .info import get_video_info
        info = await get_video_info(url)
        if info:
            filename = sanitize_filename(info.get('title', 'video'))
        else:
            filename = "video"
    
    temp_filename = f"temp_{filename}"
    full_video_path = await download_video(url, quality, temp_filename, progress_callback)
    
    if not full_video_path:
        return None
    
    # Trim with FFmpeg
    output_path = str(DOWNLOADS_PATH / f"{filename}_trimmed.mp4")
    duration = end_time - start_time
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            _executor,
            lambda: subprocess.run([
                'ffmpeg', '-y',
                '-i', full_video_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-c:v', 'libx264', '-c:a', 'aac',
                '-movflags', '+faststart',
                output_path
            ], check=True, capture_output=True)
        )
        
        # Remove temp file
        Path(full_video_path).unlink(missing_ok=True)
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg trim error: {e}")
        # Return full video as fallback
        final_path = str(DOWNLOADS_PATH / f"{filename}.mp4")
        shutil.move(full_video_path, final_path)
        return final_path
    except Exception as e:
        logger.error(f"Trim error: {e}")
        Path(full_video_path).unlink(missing_ok=True)
        return None


async def download_audio_trimmed(
    url: str,
    start_time: int,
    end_time: int,
    filename: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Download a trimmed portion of audio from YouTube.
    """
    if not filename:
        from .info import get_video_info
        info = await get_video_info(url)
        if info:
            filename = sanitize_filename(info.get('title', 'audio'))
        else:
            filename = "audio"
    
    temp_filename = f"temp_{filename}"
    full_audio_path = await download_audio(url, temp_filename, progress_callback)
    
    if not full_audio_path:
        return None
    
    # Trim with FFmpeg
    output_path = str(DOWNLOADS_PATH / f"{filename}_trimmed.mp3")
    duration = end_time - start_time
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            _executor,
            lambda: subprocess.run([
                'ffmpeg', '-y',
                '-i', full_audio_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'libmp3lame', '-q:a', '2',
                output_path
            ], check=True, capture_output=True)
        )
        
        # Remove temp file
        Path(full_audio_path).unlink(missing_ok=True)
        
        return output_path
        
    except Exception as e:
        logger.error(f"Audio trim error: {e}")
        Path(full_audio_path).unlink(missing_ok=True)
        return None


async def cleanup_downloads(max_age_hours: int = 24):
    """
    Clean up old downloaded files.
    Called periodically to prevent disk fill-up.
    """
    import time
    
    now = time.time()
    max_age_seconds = max_age_hours * 3600
    
    count = 0
    for file_path in DOWNLOADS_PATH.glob('*'):
        if file_path.is_file():
            age = now - file_path.stat().st_mtime
            if age > max_age_seconds:
                try:
                    file_path.unlink()
                    count += 1
                except Exception as e:
                    logger.error(f"Error deleting {file_path}: {e}")
    
    if count > 0:
        logger.info(f"Cleaned up {count} old download files")
    
    return count


def delete_file(file_path: str) -> bool:
    """Delete a downloaded file immediately."""
    try:
        Path(file_path).unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error deleting {file_path}: {e}")
        return False


def get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    try:
        return Path(file_path).stat().st_size
    except:
        return 0


def is_file_too_large(file_path: str) -> bool:
    """Check if file exceeds Telegram limit."""
    return get_file_size(file_path) > MAX_FILE_SIZE_BYTES
