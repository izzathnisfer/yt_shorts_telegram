"""
Configuration management for YouTube Shorts Bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DOWNLOADS_PATH = Path(os.getenv("DOWNLOADS_PATH", "./downloads"))

# Ensure directories exist
DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)

# PostgreSQL Database Configuration
DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
DATABASE_USER = os.getenv("DATABASE_USER", "postgres")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "youtube_shorts_bot")
DATABASE_PORT = int(os.getenv("DATABASE_PORT", "5432"))

# Telegram credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Validate required credentials
if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError(
        "Missing required environment variables. "
        "Please set API_ID, API_HASH, and BOT_TOKEN in .env file."
    )

# Default settings
DEFAULT_CHECK_INTERVAL = int(os.getenv("DEFAULT_CHECK_INTERVAL", "15"))  # minutes
DEFAULT_RESOLUTION = os.getenv("DEFAULT_RESOLUTION", "720")
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "20"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "2000"))  # 2GB for Pyrogram
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Video quality options
QUALITY_OPTIONS = ["360", "480", "720", "1080"]

# Check interval options (in minutes)
INTERVAL_OPTIONS = [5, 15, 30, 60]

# Daily limit options
LIMIT_OPTIONS = [10, 20, 50, 0]  # 0 = unlimited

# Quiet hours default
DEFAULT_QUIET_START = "23:00"
DEFAULT_QUIET_END = "07:00"
DEFAULT_TIMEZONE = "Asia/Kolkata"

# Lofi music sources (curated channels/playlists)
LOFI_SOURCES = [
    "https://www.youtube.com/@LofiGirl",
    "https://www.youtube.com/@ChillhopMusic", 
    "https://www.youtube.com/@thebootlegboy2",
    "https://www.youtube.com/@dreamhop",
]

# Search result limits
SEARCH_RESULTS_LIMIT = 5
CHANNEL_VIDEOS_LIMIT = 10

# yt-dlp configuration
YTDLP_FORMAT = "bestvideo[ext=mp4][height<=%(quality)s]+bestaudio[ext=m4a]/best[ext=mp4][height<=%(quality)s]/best"
YTDLP_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
COOKIES_PATH = BASE_DIR / "cookies.txt"  # Place your cookies.txt here

# Telegram message limits
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096

# Rate limiting
MIN_CHECK_INTERVAL = 5  # minimum minutes between checks
MAX_CONCURRENT_DOWNLOADS = 2

# Cache settings
VIDEO_CACHE_HOURS = 24  # hours to keep downloaded videos info
LOFI_CACHE_HOURS = 168  # 1 week for lofi tracks

# Weekly report day (0 = Monday, 6 = Sunday)
WEEKLY_REPORT_DAY = 6  # Sunday
WEEKLY_REPORT_HOUR = 10  # 10 AM

# Bot messages
BOT_NAME = "YouTube Shorts Bot"
BOT_USERNAME = "youtube_shorts_bot"
