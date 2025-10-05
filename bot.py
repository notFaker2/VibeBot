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
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB Telegram limit

# --- Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Helper: yt-dlp options ---
def get_ydl_opts(format_string: str, outtmpl: str = None):
    ydl_opts = {
        'format': format_string,
        'quiet': True,
        'nocheckcertificate': True,
        'noprogress': True,
    }
    if os.path.exists("cookies.txt"):  # auto use cookies.txt if available
        ydl_opts['cookies'] = "cookies.txt"
    if outtmpl:
        ydl_opts['outtmpl'] = outtmpl
    return ydl_opts

# --- Bot Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Hi {user_name}! 👋\n\n"
        "I'm your YouTube Downloader Bot!\n\n"
        "Send me a YouTube link and choose whether you want 🎬 Video or 🎵 Audio.\n\n"
        "⚠️ Note: Telegram bots can only send files up to 50MB."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📌 How to use me:\n"
        "1. Copy a YouTube link.\n"
        "2. Send it to me.\n"
        "3. Choose 🎬 Video or 🎵 Audio.\n\n"
        "⚠️ Videos larger than 50 MB cannot be uploaded to Telegram.\n"
        "🔑 If you see errors like 'Sign in to confirm', add a cookies.txt file."
    )
    await update.message.reply_text(help_text)

def is_valid_youtube_url(url: str) -> bool:
    youtube_domains = ['youtube.com', 'youtu.be']
    return any(domain in url for domain in youtube_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text.strip()
    if not is_valid_youtube_url(message_text):
        await update.message.reply_text("❌ Not a valid YouTube link. Please send a proper link.")
        return

    context.user_data['url'] = message_text
    keyboard = [
        [InlineKeyboardButton("🎬 Video", callback_data='download_video'),
         InlineKeyboardButton("🎵 Audio", callback_data='download_audio')],
        [InlineKeyboardButton("🎬+🎵 Both", callback_data='download_both')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose what you want to download:", reply_markup=reply_markup)

# --- Callback Logic ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    url = context.user_data.get('url')
    chat_id = query.message.chat_id

    if not url:
        await query.edit_message_text("❌ I lost the link. Please send it again.")
        return

    await query.edit_message_text("Processing your request... ⚙️")

    if choice in ['download_video', 'download_both']:
        await download_and_send_video(context, chat_id, url)

    if choice in ['download_audio', 'download_both']:
        await download_and_send_audio(context, chat_id, url)

    await context.bot.send_message(chat_id=chat_id, text="✅ Done!")

# --- Download Video ---
async def download_and_send_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    video_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking video details...")

    try:
        with yt_dlp.YoutubeDL(get_ydl_opts('bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best')) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ Video too large ({filesize/1024/1024:.2f} MB). Limit is 50 MB.",
                    chat_id=chat_id, message_id=status_msg.message_id
                )
                return False

        await context.bot.edit_message_text("Downloading video... 🎬", chat_id=chat_id, message_id=status_msg.message_id)
        with yt_dlp.YoutubeDL(get_ydl_opts('bestvideo+bestaudio/best', os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'))) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)

        await context.bot.edit_message_text("Uploading video... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_video(chat_id=chat_id, video=open(video_path, 'rb'),
                                     supports_streaming=True, caption=info.get('title', 'YouTube Video'))
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True

    except yt_dlp.utils.DownloadError as e:
        msg = "❌ Download Failed: This video may be age-restricted/private. Add cookies.txt to fix."
        await context.bot.edit_message_text(msg, chat_id=chat_id, message_id=status_msg.message_id)
        return False
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)

# --- Download Audio ---
async def download_and_send_audio(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    audio_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking audio details...")

    try:
        with yt_dlp.YoutubeDL(get_ydl_opts('bestaudio[ext=m4a]/bestaudio')) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ Audio too large ({filesize/1024/1024:.2f} MB). Limit is 50 MB.",
                    chat_id=chat_id, message_id=status_msg.message_id
                )
                return False

        await context.bot.edit_message_text("Downloading audio... 🎵", chat_id=chat_id, message_id=status_msg.message_id)
        with yt_dlp.YoutubeDL(get_ydl_opts('bestaudio[ext=m4a]/bestaudio', os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'))) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_path = ydl.prepare_filename(info)

        await context.bot.edit_message_text("Uploading audio... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_audio(chat_id=chat_id, audio=open(audio_path, 'rb'),
                                     title=info.get('title', 'YouTube Audio'),
                                     performer=info.get('uploader', 'Uploader'))
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True

    except yt_dlp.utils.DownloadError:
        msg = "❌ Download Failed: This audio may be age-restricted/private. Add cookies.txt to fix."
        await context.bot.edit_message_text(msg, chat_id=chat_id, message_id=status_msg.message_id)
        return False
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

# --- Main ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN missing. Set it in environment variables.")
        return

    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is now polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
