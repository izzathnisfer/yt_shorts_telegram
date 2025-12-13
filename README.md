# YouTube Shorts Bot 🎬

A powerful Telegram bot for mindful YouTube consumption with URL leeching, Nextcloud integration, and comprehensive admin tools.

## ✨ Features

### 📺 YouTube Integration
- **Channel Subscriptions** - Subscribe to channels, get notifications for new videos
- **Shorts Auto-Delivery** - Auto-download and send YouTube Shorts directly
- **Smart Search** - Search YouTube from within Telegram
- **Video Downloads** - Download videos with quality selection
- **Audio Extraction** - Download audio-only (MP3)
- **Trimming** - Download specific portions of videos

### 📥 URL Leeching
- **Direct URL Downloads** - Download files from any direct URL
- **Telegram Upload** - Upload downloaded files to Telegram (up to 2GB)
- **Nextcloud Upload** - Upload to your private cloud with auto-delete
- **Real-time Progress** - Live progress bar during download/upload
- **Task Management** - Cancel running tasks, per-user limits

### ☁️ Nextcloud Integration
- **WebDAV Uploads** - Direct upload to your Nextcloud
- **Share Links** - Auto-generate shareable links
- **Auto-Delete** - Configurable timer for automatic cleanup
- **Secure Storage** - Credentials stored with encoding in PostgreSQL

### 🧘 Mindful Viewing
- **Watch Queue** - Save videos to watch later intentionally
- **Focus Mode** - Pause notifications during work/study
- **Daily Limits** - Set maximum videos per day
- **Quiet Hours** - No notifications during set hours
- **Lofi Study Mode** - Get lofi music for focused studying

### 📊 Statistics & Analytics
- **Time Optimization Score** - 0-100 score for mindful viewing
- **Daily/Weekly/All-time Stats** - Track your viewing habits
- **Top Channels** - See where you spend most time
- **Time Saved Estimate** - See how much time you've saved

### 🔧 Admin Panel
- **Bot Summary** - Users, subscriptions, content stats
- **System Monitoring** - CPU, RAM, disk usage
- **User Management** - View all users with details
- **Broadcast Messages** - Send announcements to all users
- **Task Monitoring** - View and manage active leech tasks
- **Storage Management** - Clean up old files

### 💾 Data Management
- **Favorites** - Save favorite videos for quick access
- **Export/Import** - Backup and restore all your data
- **Priority Channels** - Mark channels to bypass quiet hours

## 🚀 Setup

### Prerequisites
- Python 3.9+
- PostgreSQL database
- FFmpeg

### Installation

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd youtube-shorts-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with:
   ```
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   DB_HOST=localhost
   DB_USER=postgres
   DB_PASSWORD=password
   DB_NAME=youtube_shorts
   ADMIN_USERS=your_telegram_user_id
   ```

4. **Install FFmpeg**
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

5. **Run the bot**
   ```bash
   python main.py
   ```

## 📋 Commands

### Content
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
| `/sync` | Download all queued videos |

### Focus & Music
| Command | Description |
|---------|-------------|
| `/lofi` | Get lofi study music |
| `/focus <duration>` | Enable focus mode |
| `/limit <number>` | Set daily watch limit |

### Leeching
| Command | Description |
|---------|-------------|
| `/l <url>` | Download URL → Telegram |
| `/ld <url>` | Download URL → Nextcloud |
| `/setnc` | Configure Nextcloud settings |

### Settings & Stats
| Command | Description |
|---------|-------------|
| `/stats` | View your statistics |
| `/favorites` | View saved videos |
| `/settings` | All preferences |
| `/export` | Export your data |
| `/admin` | Admin panel (admins only) |
| `/help` | Help & commands |

## 📁 Project Structure

```
├── main.py              # Entry point
├── config.py            # Configuration
├── database.py          # PostgreSQL operations
├── tg_bot/              # Telegram integration
│   ├── bot.py           # Handler registration
│   ├── uploader.py      # Pyrogram uploader (2GB)
│   └── keyboards.py     # UI components
├── handlers/            # Command handlers
│   ├── leech.py         # URL leeching
│   ├── leech_admin.py   # Admin panel
│   ├── leech_nextcloud.py # NC settings
│   └── ...
├── youtube/             # YouTube integration
│   ├── downloader.py    # Download videos
│   ├── search.py        # Search functionality
│   └── info.py          # Video info extraction
└── services/            # Background services
    ├── scheduler.py     # Periodic tasks
    ├── leech_data.py    # Leech data storage
    └── bot_stats.py     # Centralized stats
```

## ⚡ Resource Optimization

Designed for low-resource environments (512MB RAM):
- Streaming downloads (no full file in memory)
- Immediate cleanup after uploads
- Efficient PostgreSQL connection pooling
- Async operations throughout
- Progress throttling to reduce API calls

## 🔒 Security

- Nextcloud credentials stored with base64 encoding in PostgreSQL
- Admin-only access to sensitive operations
- Per-user task isolation

## 📄 License

MIT
