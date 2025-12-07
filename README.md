# YouTube Shorts Bot

A Telegram bot that helps you consume YouTube content mindfully, without the endless scrolling.

## Features

- 📺 **Channel Subscriptions** - Subscribe to YouTube channels and receive notifications
- 🎬 **Shorts Delivery** - Auto-download and send YouTube Shorts directly
- 🔍 **Search** - Search YouTube from Telegram
- 📥 **Watch Queue** - Save videos to watch later
- 🎧 **Lofi Study Mode** - Get lofi music for focused studying
- 🧘 **Focus Mode** - Pause notifications during work
- 📊 **Daily Limits** - Set daily watch limits
- 📈 **Statistics** - Track your viewing habits
- ⭐ **Favorites** - Save favorite videos
- 💾 **Export/Import** - Backup and restore your data

## Setup

1. **Clone the repository**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your credentials:
   - `API_ID` and `API_HASH` from https://my.telegram.org
   - `BOT_TOKEN` from @BotFather

4. **Install FFmpeg** (required for audio/video processing)
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

5. **Run the bot**
   ```bash
   python main.py
   ```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/subscribe` | Subscribe to a channel |
| `/list` | View subscribed channels |
| `/search <query>` | Search YouTube |
| `/download <url>` | Download a video |
| `/audio <url>` | Download audio only |
| `/queue` | View watch queue |
| `/lofi` | Get lofi study music |
| `/focus <duration>` | Enable focus mode |
| `/stats` | View statistics |
| `/settings` | Bot settings |
| `/help` | Help & commands |

## Project Structure

```
├── main.py              # Entry point
├── config.py            # Configuration
├── database.py          # Database operations
├── telegram/            # Telegram integration
│   ├── bot.py           # Bot setup
│   ├── uploader.py      # Pyrogram uploader (2GB)
│   └── keyboards.py     # UI components
├── handlers/            # Command handlers
├── youtube/             # YouTube integration
│   ├── downloader.py    # Download videos
│   ├── search.py        # Search functionality
│   ├── info.py          # Video info extraction
│   └── utils.py         # Utilities
├── services/            # Background services
│   └── scheduler.py     # Periodic tasks
└── templates/           # Message templates
```

## Resource Optimization

Designed for low-resource environments (512MB RAM):
- Streaming downloads (no full file in memory)
- Immediate cleanup after uploads
- Sequential processing
- Connection pooling
- Async SQLite operations

## License

MIT
