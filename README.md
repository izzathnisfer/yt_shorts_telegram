# YouTube Shorts Bot 🎬

A powerful Telegram bot for mindful YouTube consumption with smart notifications, snooze reminders, URL leeching, and Nextcloud integration.

## ✨ Features

### 📺 YouTube Integration
- **Channel Subscriptions** - Subscribe to channels, get notifications for new videos
- **Smart Notifications** - Only notifies for videos uploaded AFTER you subscribed
- **Snooze Reminders** - Snooze notifications (1h, 12h, 1d, 3d, 1w, 1m)
- **No Duplicates** - Never receive the same notification twice
- **Shorts Auto-Delivery** - Auto-download and send YouTube Shorts directly
- **Smart Search** - Search YouTube from within Telegram
- **Video Downloads** - Download videos with quality selection (360p-1080p)
- **Audio Extraction** - Download audio-only (MP3)

### 📥 URL Leeching
- **Direct URL Downloads** - Download files from any direct URL
- **Telegram Upload** - Upload downloaded files to Telegram (up to 2GB)
- **Nextcloud Upload** - Upload to your private cloud with auto-delete
- **Real-time Progress** - Live progress bar during download/upload

### ☁️ Nextcloud Integration
- **WebDAV Uploads** - Direct upload to your Nextcloud
- **Share Links** - Auto-generate shareable links
- **Auto-Delete** - Configurable timer for automatic cleanup

### 🧘 Mindful Viewing
- **Watch Queue** - Save videos to watch later intentionally
- **Focus Mode** - Pause notifications during work/study
- **Daily Limits** - Set maximum videos per day
- **Quiet Hours** - No notifications during set hours
- **Lofi Study Mode** - Get lofi music for focused studying

### 📊 Statistics & Admin
- **Time Optimization Score** - 0-100 score for mindful viewing
- **Daily/Weekly Stats** - Track your viewing habits
- **Admin Panel** - Bot summary, system monitoring, broadcast, storage cleanup
- **Notification Config** - Admin can set check interval (5/10/15/30/60 mins)

## 🚀 Server Deployment (AWS EC2 / Linux)

### One-Line Setup
```bash
git clone <repo-url> && cd youtube-shorts-bot && chmod +x setup_server.sh && ./setup_server.sh
```

### Run the Bot
```bash
# Foreground (for testing)
source venv/bin/activate && python main.py

# Background (production)
source venv/bin/activate && nohup python main.py > bot.log 2>&1 &
```

### Update & Restart
```bash
git pull && source venv/bin/activate && pkill -f "python main.py"; nohup python main.py > bot.log 2>&1 &
```

## 💻 Local Development

### Prerequisites
- Python 3.12+
- PostgreSQL database
- FFmpeg

### Installation

1. **Clone and install**
   ```bash
   git clone <repo-url>
   cd youtube-shorts-bot
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env`:
   ```
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   DATABASE_HOST=localhost
   DATABASE_USER=postgres
   DATABASE_PASSWORD=password
   DATABASE_NAME=youtube_shorts
   ADMIN_USERS=your_telegram_user_id
   ```

3. **Install FFmpeg**
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

4. **Run**
   ```bash
   python main.py
   ```

## 📋 Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/subscribe` | Subscribe to a channel |
| `/unsubscribe` | Unsubscribe from a channel |
| `/list` | View subscribed channels |
| `/search <query>` | Search YouTube |
| `/download <url>` | Download a video |
| `/audio <url>` | Download audio only |
| `/queue` | View watch queue |
| `/lofi` | Get lofi study music |
| `/focus <duration>` | Enable focus mode |
| `/stats` | View your statistics |
| `/settings` | All preferences |
| `/l <url>` | Download URL → Telegram |
| `/ld <url>` | Download URL → Nextcloud |
| `/admin` | Admin panel (admins only) |

## 📁 Project Structure

```
├── main.py              # Entry point
├── config.py            # Configuration
├── database.py          # PostgreSQL operations
├── setup_server.sh      # Server deployment script
├── tg_bot/              # Telegram integration
├── handlers/            # Command handlers
│   ├── snooze.py        # Snooze feature
│   └── ...
├── youtube/             # YouTube integration
│   └── downloader.py    # yt-dlp downloads
└── services/
    └── scheduler.py     # Batch notifications
```

## 🔧 Tech Stack

- **Python 3.12** - Latest stable Python
- **yt-dlp** - YouTube downloads
- **python-telegram-bot** - Telegram API
- **Pyrogram** - Large file uploads (2GB)
- **PostgreSQL** - Persistent storage
- **FFmpeg** - Audio/video processing

## 📄 License

MIT
