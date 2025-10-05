# --- Helper: YDL options with cookies ---
def get_ydl_opts(format_string: str, outtmpl: str = None):
    ydl_opts = {
        'format': format_string,
        'quiet': True,
        'nocheckcertificate': True,
        'noprogress': True,
    }
    # Use cookies.txt if available
    if os.path.exists("cookies.txt"):
        ydl_opts['cookies'] = "cookies.txt"
    if outtmpl:
        ydl_opts['outtmpl'] = outtmpl
    return ydl_opts


# --- Download Video ---
async def download_and_send_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    video_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking video details...")

    try:
        # First check size
        with yt_dlp.YoutubeDL(get_ydl_opts('bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best')) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            
            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ **Error:** The video is larger than 50 MB. File size: {filesize/1024/1024:.2f} MB",
                    chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
                )
                return False

        # Download
        await context.bot.edit_message_text(text="Downloading video... 🎬", chat_id=chat_id, message_id=status_msg.message_id)
        with yt_dlp.YoutubeDL(get_ydl_opts('bestvideo+bestaudio/best', os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'))) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)

        # Upload
        await context.bot.edit_message_text(text="Uploading video... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_video(chat_id=chat_id, video=open(video_path, 'rb'),
                                     supports_streaming=True, caption=info.get('title', 'YouTube Video'))
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        return True
    except Exception as e:
        logger.error(f"Error downloading video: {e}", exc_info=True)
        await context.bot.edit_message_text(text=f"Sorry, an error occurred while processing the video. 😔", chat_id=chat_id, message_id=status_msg.message_id)
        return False
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)


# --- Download Audio ---
async def download_and_send_audio(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str) -> bool:
    audio_path = None
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Checking audio details...")

    try:
        # Check size
        with yt_dlp.YoutubeDL(get_ydl_opts('bestaudio[ext=m4a]/bestaudio')) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get('filesize') or info.get('filesize_approx')
            
            if not filesize or filesize > MAX_FILE_SIZE_BYTES:
                await context.bot.edit_message_text(
                    text=f"❌ **Error:** The audio is larger than 50 MB. File size: {filesize/1024/1024:.2f} MB",
                    chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
                )
                return False

        # Download
        await context.bot.edit_message_text(text="Downloading audio... 🎵", chat_id=chat_id, message_id=status_msg.message_id)
        with yt_dlp.YoutubeDL(get_ydl_opts('bestaudio[ext=m4a]/bestaudio', os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'))) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_path = ydl.prepare_filename(info)

        # Upload
        await context.bot.edit_message_text(text="Uploading audio... 🚀", chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_audio(chat_id=chat_id, audio=open(audio_path, 'rb'),
                                     title=info.get('title', 'YouTube Audio'),
                                     performer=info.get('uploader', 'Uploader'))
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

