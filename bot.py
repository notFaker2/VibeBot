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

# Load environment variables
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit

# --- Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ensure download directory exists
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Hi {user_name}! 👋\n\n"
        "I'm your YouTube Downloader Bot running on Render! 🚀\n\n"
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
        "⚠️ Please note: Telegram bots have a file size limit of 50 MB. "
        "I will let you know if the requested file is too large."
    )
    await update.message.reply_text(help_text)

def is_valid_youtube_url(url: str) -> bool:
    """Checks if the provided text is a valid YouTube URL."""
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
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

    await query.edit_message_text(text="Request received! Processing... ⚙️")

    video_success = False
    audio_success = False

    if choice in ['download_video', 'download_both']:
        video_success = await download_and_send_video(context, chat_id, url)
    
    if choice in ['download_audio', 'download_both']:
        # For 'both', only download audio if video was successful
        if choice == 'download_both' and not video_success:
            await context.bot.send_message(chat_id=chat_id, text="Skipping audio download since video failed.")
        else:
            audio_success = await download_and_send_audio(context, chat_id, url)
    
    # Send a final completion message
    if choice == 'download_video' and video_success:
        await context.bot.send_message(chat_id=chat_id, text="Video download complete! ✅")
    elif choice == 'download_audio' and audio_success:
        await context.bot.send_message(chat_id=chat_id, text="Audio download complete! ✅")
    elif choice == 'download_both':
        if video_success and audio_success:
            await context.bot.send_message(chat_id=chat_id, text="Both video and audio downloads complete! ✅")
        elif video_success or audio_success:
            await context.bot.send_message(chat_id=chat_id, text="Downloads completed with partial success.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Both downloads failed. Please try again.")

def get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(file_path)

async def download_and_send_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    """Downloads, sends, and cleans up a video file."""
    video_path = None
    status_msg = None
    try:
        status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking video... 📹")
        
        ydl_opts = {
            'format': 'best[height<=720][ext=mp4]',  # Limit to 720p for size
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First check file size
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            
            if filesize and filesize > MAX_FILE_SIZE:
                size_mb = filesize / 1024 / 1024
                await context.bot.edit_message_text(
                    text=f"❌ Video too large ({size_mb:.1f} MB). Max 50 MB.",
                    chat_id=chat_id, 
                    message_id=status_msg.message_id
                )
                return False

            await context.bot.edit_message_text(text="Downloading video... 🎬", chat_id=chat_id, message_id=status_msg.message_id)
            ydl.download([url])
            video_path = ydl.prepare_filename(info)

        # Check actual file size
        actual_size = get_file_size(video_path)
        if actual_size > MAX_FILE_SIZE:
            await context.bot.edit_message_text(
                text=f"❌ Downloaded video too large ({actual_size/1024/1024:.1f} MB).",
                chat_id=chat_id, 
                message_id=status_msg.message_id
            )
            return False

        await context.bot.edit_message_text(text="Uploading video... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id, 
                video=video_file, 
                supports_streaming=True, 
                caption=info.get('title', 'YouTube Video')[:1000]
            )
        
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True

    except yt_dlp.utils.DownloadError as e:
        error_msg = "❌ Download failed. Video might be private, restricted, or unavailable."
        if status_msg:
            await context.bot.edit_message_text(text=error_msg, chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        return False
        
    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)
        error_msg = "❌ An error occurred while processing the video."
        if status_msg:
            await context.bot.edit_message_text(text=error_msg, chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        return False
        
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                logger.info(f"Cleaned up video file: {video_path}")
            except Exception as e:
                logger.error(f"Error cleaning up video file: {e}")

async def download_and_send_audio(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    """Downloads, sends, and cleans up an audio file."""
    audio_path = None
    status_msg = None
    try:
        status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking audio... 🎵")
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s_audio.%(ext)s'),
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First check file size
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            
            if filesize and filesize > MAX_FILE_SIZE:
                size_mb = filesize / 1024 / 1024
                await context.bot.edit_message_text(
                    text=f"❌ Audio too large ({size_mb:.1f} MB). Max 50 MB.",
                    chat_id=chat_id, 
                    message_id=status_msg.message_id
                )
                return False

            await context.bot.edit_message_text(text="Downloading audio... 🎵", chat_id=chat_id, message_id=status_msg.message_id)
            ydl.download([url])
            audio_path = ydl.prepare_filename(info)

        # Check actual file size
        actual_size = get_file_size(audio_path)
        if actual_size > MAX_FILE_SIZE:
            await context.bot.edit_message_text(
                text=f"❌ Downloaded audio too large ({actual_size/1024/1024:.1f} MB).",
                chat_id=chat_id, 
                message_id=status_msg.message_id
            )
            return False

        await context.bot.edit_message_text(text="Uploading audio... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        
        with open(audio_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=chat_id, 
                audio=audio_file, 
                title=info.get('title', 'YouTube Audio')[:64],
                performer=info.get('uploader', 'Uploader')[:64]
            )
        
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True
        
    except yt_dlp.utils.DownloadError as e:
        error_msg = "❌ Download failed. Audio might be from a private or restricted video."
        if status_msg:
            await context.bot.edit_message_text(text=error_msg, chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        return False
        
    except Exception as e:
        logger.error(f"Error processing audio: {e}", exc_info=True)
        error_msg = "❌ An error occurred while processing the audio."
        if status_msg:
            await context.bot.edit_message_text(text=error_msg, chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        return False
        
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Cleaned up audio file: {audio_path}")
            except Exception as e:
                logger.error(f"Error cleaning up audio file: {e}")

def main():
    """Starts the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Please set it in environment variables.")
        return

    logger.info("Starting Telegram Bot on Render...")
    
    # Create the Application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is now running with polling...")
    app.run_polling()

if __name__ == '__main__':
    main()