#!/bin/bash
# YouTube Shorts Bot - Server Setup Script
# Run this on your AWS EC2 instance

set -e

echo "🚀 Setting up YouTube Shorts Bot..."

# Update system packages
sudo apt-get update -y

# Install ffmpeg (required for audio/video processing)
echo "📦 Installing ffmpeg..."
sudo apt-get install -y ffmpeg

# Install Python 3.11 if not present
echo "🐍 Checking Python..."
if ! command -v python3.11 &> /dev/null; then
    sudo apt-get install -y python3.11 python3.11-venv python3-pip
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade pip
pip install --upgrade pip

# Install requirements
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Verify ffmpeg is installed
echo "✅ Verifying ffmpeg installation..."
ffmpeg -version | head -1

echo "✅ Setup complete!"
echo ""
echo "To run the bot:"
echo "  source venv/bin/activate && python main.py"
echo ""
echo "To run in background with nohup:"
echo "  nohup python main.py > bot.log 2>&1 &"
