# Use official Python runtime
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for yt-dlp & ffmpeg)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Set environment variables (will be overridden in Northflank dashboard)
ENV TELEGRAM_BOT_TOKEN=""
ENV PORT=8080

# Start the bot
CMD ["python", "bot.py"]
