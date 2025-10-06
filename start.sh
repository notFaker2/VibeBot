#!/bin/bash
# Install ffmpeg
apt-get update && apt-get install -y ffmpeg

# Create downloads directory
mkdir -p downloads

# Start the bot
python bot.py