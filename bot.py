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

# Load environment variables from a .env file
load_dotenv()

# --- Configuration ---
# Your bot token is now securely loaded from the .env file
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DOWNLOAD_DIR = "downloads"
# Telegram's file size limit for bots is 50MB
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024 

# --- Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ensure the download directory exists
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Hi {user_name}! 👋\n\n"
        "I'm your 24/7 YouTube Downloader Bot!\n\n"
        "Just send me a YouTube link, and I'll help you download the video or audio. "
        "Files must be under 50MB to be uploaded to Telegram."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message when the /help command is issued."""
    help_text = (
        "How to use me:\n"
        "1. Find a video on YouTube.\n"
        "2. Copy its link.\n"
        "3. Paste the link here and send it to me.\n\n"
        "I will then ask what you want to download. You can choose:\n"
        "🎬 Video only\n"
        "🎵 Audio only\n"
        "🎬+🎵 Both video and audio\n\n"
        "⚠️ Please note: Telegram bots have a file size limit of 50 MB. I will let you know if the requested file is too large."
    )
    await update.message.reply_text(help_text)

def is_valid_youtube_url(url: str) -> bool:
    """Checks if the provided text is a valid YouTube URL."""
    # A simple but effective check for most YouTube URL formats
    youtube_domains = ['youtube.com', 'youtu.be']
    return any(domain in url for domain in youtube_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages, validates YouTube URL, and shows download options."""
    message_text = update.message.text.strip()
    
    if not is_valid_youtube_url(message_text):
        await update.message.reply_text("That doesn't look like a valid YouTube link. Please send a valid YouTube URL!")
        return

    context.user_data['url'] = message_text

    keyboard = [
        [
            InlineKeyboardButton("🎬 Video", callback_data='download_video'),
            InlineKeyboardButton("🎵 Audio", callback_data='download_audio')
        ],
        [InlineKeyboardButton("🎬+🎵 Both", callback_data='download_both')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose what you want to download:', reply_markup=reply_markup)

# --- Callback and Download Logic ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses the CallbackQuery and runs the appropriate download function."""
    query = update.callback_query
    await query.answer()

    choice = query.data
    url = context.user_data.get('url')
    chat_id = query.message.chat_id

    if not url:
        await query.edit_message_text(text="Sorry, I seem to have lost the link. Please send it again.")
        return

    await query.edit_message_text(text="Request received! Checking details... ⚙️")

    if choice in ['download_video', 'download_both']:
        await download_and_send_video(context, chat_id, url)
    
    if choice in ['download_audio', 'download_both']:
        await download_and_send_audio(context, chat_id, url)
    
    await context.bot.send_message(chat_id=chat_id, text="All tasks complete! ✅")

async def download_and_send_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    """Checks video size, then downloads, sends, and cleans up the video file."""
    video_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking video details...")
    try:
        ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            
            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ **Error:** The video is larger than 50 MB and cannot be uploaded to Telegram. File size: {filesize / 1024 / 1024:.2f} MB",
                    chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
                )
                return False

        await context.bot.edit_message_text(text="Downloading video... 🎬", chat_id=chat_id, message_id=status_msg.message_id)
        ydl_opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            video_path = ydl.prepare_filename(info)
        
        await context.bot.edit_message_text(text="Uploading video... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_video(chat_id=chat_id, video=open(video_path, 'rb'), supports_streaming=True, caption=info.get('title', 'YouTube Video'))
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True
    except Exception as e:
        logger.error(f"Error downloading video: {e}", exc_info=True)
        await context.bot.edit_message_text(text=f"Sorry, an error occurred while processing the video. 😔", chat_id=chat_id, message_id=status_msg.message_id)
        return False
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Cleaned up video file: {video_path}")

async def download_and_send_audio(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    """Checks audio size, then downloads, sends, and cleans up the audio file."""
    audio_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking audio details...")
    try:
        ydl_opts = {'format': 'bestaudio[ext=m4a]/bestaudio'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')

            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ **Error:** The audio is larger than 50 MB and cannot be uploaded to Telegram. File size: {filesize / 1024 / 1024:.2f} MB",
                    chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
                )
                return False
        
        await context.bot.edit_message_text(text="Downloading audio... 🎵", chat_id=chat_id, message_id=status_msg.message_id)
        ydl_opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            audio_path = ydl.prepare_filename(info)

        await context.bot.edit_message_text(text="Uploading audio... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_audio(chat_id=chat_id, audio=open(audio_path, 'rb'), title=info.get('title', 'YouTube Audio'), performer=info.get('uploader', 'Uploader'))
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True
    except Exception as e:
        logger.error(f"Error downloading audio: {e}", exc_info=True)
        await context.bot.edit_message_text(text=f"Sorry, an error occurred while processing the audio. 😔", chat_id=chat_id, message_id=status_msg.message_id)
        return False
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"Cleaned up audio file: {audio_path}")

def main():
    """Starts the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN is not defined in the environment variables.")
        return

    logger.info("Starting bot...")
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is now polling for updates.")
    app.run_polling()

if __name__ == '__main__':
    main()

