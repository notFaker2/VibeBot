import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
import yt_dlp
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024
PORT = int(os.getenv('PORT', 10000))  # For Render compatibility

# --- Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Your existing bot handlers and functions remain the same ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Hi {user_name}! 👋\n\n"
        "I'm your YouTube Downloader Bot running on Render! 🚀\n\n"
        "Just send me a YouTube link to download video or audio."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "How to use me:\n"
        "1. Send a YouTube link\n"
        "2. Choose video or audio\n"
        "3. I'll download it for you!\n\n"
        "Note: Some videos might not be available due to restrictions."
    )
    await update.message.reply_text(help_text)

def is_valid_youtube_url(url: str) -> bool:
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
    return any(domain in url for domain in youtube_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text.strip()
    
    if not is_valid_youtube_url(message_text):
        await update.message.reply_text("Please send a valid YouTube URL!")
        return

    context.user_data['url'] = message_text

    keyboard = [
        [InlineKeyboardButton("🎬 Video", callback_data='download_video'),
         InlineKeyboardButton("🎵 Audio", callback_data='download_audio')],
        [InlineKeyboardButton("🎬+🎵 Both", callback_data='download_both')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Choose download type:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data
    url = context.user_data.get('url')
    chat_id = query.message.chat_id

    if not url:
        await query.edit_message_text(text="Please send the link again.")
        return

    await query.edit_message_text(text="Processing your request... ⚙️")

    video_success = False
    audio_success = False

    if choice in ['download_video', 'download_both']:
        video_success = await download_and_send_media(context, chat_id, url, 'video')
    
    if choice in ['download_audio', 'download_both']:
        if choice == 'download_both' and not video_success:
            await context.bot.send_message(chat_id=chat_id, text="Skipping audio since video failed.")
        else:
            audio_success = await download_and_send_media(context, chat_id, url, 'audio')
    
    # Completion message
    if choice == 'download_video' and video_success:
        await context.bot.send_message(chat_id=chat_id, text="Video download complete! ✅")
    elif choice == 'download_audio' and audio_success:
        await context.bot.send_message(chat_id=chat_id, text="Audio download complete! ✅")
    elif choice == 'download_both':
        if video_success and audio_success:
            await context.bot.send_message(chat_id=chat_id, text="Both downloads complete! ✅")
        elif video_success or audio_success:
            await context.bot.send_message(chat_id=chat_id, text="Partial success - some downloads completed.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="All downloads failed. The video might be restricted.")

async def download_and_send_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str, media_type: str) -> bool:
    """Universal function for both video and audio downloads"""
    file_path = None
    status_msg = None
    
    try:
        status_msg = await context.bot.send_message(chat_id=chat_id, text=f"Preparing {media_type}...")
        
        ydl_opts = {
            'format': 'best[height<=480][ext=mp4]/best[ext=mp4]/best' if media_type == 'video' else 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'%(id)s_{media_type}.%(ext)s'),
            'quiet': True,
            'no_warnings': False,
            'ignoreerrors': True,
            'retries': 3,
            'fragment_retries': 3,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            },
        }
        
        # Add cookies if available
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Try to get info first
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                await context.bot.edit_message_text(
                    text=f"❌ Cannot access this video. It might be private or restricted.",
                    chat_id=chat_id, 
                    message_id=status_msg.message_id
                )
                return False
            
            # Check file size
            filesize = info.get('filesize') or info.get('filesize_approx')
            if filesize and filesize > MAX_FILE_SIZE:
                size_mb = filesize / 1024 / 1024
                await context.bot.edit_message_text(
                    text=f"❌ File too large ({size_mb:.1f} MB). Max 50 MB.",
                    chat_id=chat_id, 
                    message_id=status_msg.message_id
                )
                return False

            # Download
            await context.bot.edit_message_text(
                text=f"Downloading {media_type}... {'🎬' if media_type == 'video' else '🎵'}",
                chat_id=chat_id, 
                message_id=status_msg.message_id
            )
            
            ydl.download([url])
            file_path = ydl.prepare_filename(info)

        if not os.path.exists(file_path):
            await context.bot.edit_message_text(
                text=f"❌ Download failed - file not found.",
                chat_id=chat_id, 
                message_id=status_msg.message_id
            )
            return False

        # Check final file size
        actual_size = os.path.getsize(file_path)
        if actual_size > MAX_FILE_SIZE:
            await context.bot.edit_message_text(
                text=f"❌ Downloaded file too large ({actual_size/1024/1024:.1f} MB).",
                chat_id=chat_id, 
                message_id=status_msg.message_id
            )
            return False

        # Upload
        await context.bot.edit_message_text(
            text=f"Uploading {media_type}... 🚀",
            chat_id=chat_id, 
            message_id=status_msg.message_id
        )
        
        with open(file_path, 'rb') as media_file:
            if media_type == 'video':
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=media_file,
                    supports_streaming=True,
                    caption=info.get('title', 'YouTube Video')[:1000]
                )
            else:  # audio
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=media_file,
                    title=info.get('title', 'YouTube Audio')[:64],
                    performer=info.get('uploader', 'Uploader')[:64]
                )
        
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True
        
    except Exception as e:
        logger.error(f"Error processing {media_type}: {e}", exc_info=True)
        error_msg = f"❌ Error processing {media_type}."
        if status_msg:
            await context.bot.edit_message_text(text=error_msg, chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        return False
        
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    logger.info(f"Starting bot on Render (Port: {PORT})...")
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is running with polling...")
    
    # For Render - just use polling, no webhook setup needed
    app.run_polling()

if __name__ == '__main__':
    main()