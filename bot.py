import os
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    FloodWait, RPCError, FileReferenceExpired, 
    FileIdInvalid, FilePartMissing, AuthKeyUnregistered
)
from config import API_ID, API_HASH, BOT_TOKEN, MAX_FILE_SIZE
from database import Database
from helpers import get_human_size, clean_downloads

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Client(
    "rename_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    sleep_threshold=60
)

db = Database()

# Global error handler
async def handle_error(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except FloodWait as e:
        logger.warning(f"Flood wait: {e.value} seconds")
        await asyncio.sleep(e.value + 5)
        return await func(*args, **kwargs)
    except (FileReferenceExpired, FileIdInvalid):
        logger.error("File reference expired or invalid")
        return None
    except FilePartMissing as e:
        logger.error(f"File part missing: {e}")
        return None
    except AuthKeyUnregistered:
        logger.error("Auth key unregistered")
        return None
    except RPCError as e:
        logger.error(f"RPC Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in {func.__name__}: {e}")
        return None

# Start command
@app.on_message(filters.command(["start"]))
async def start_command(client, message: Message):
    try:
        user_id = message.from_user.id
        await db.add_user(user_id)
        
        welcome_text = """
🤖 **Welcome to File Rename Bot**

I can help you rename any file easily!

**How to use:**
1. Send me any file (document, video, audio, image)
2. Reply with `/rename new_filename`
   OR
   Use caption: `/rename new_filename`

**Commands:**
• /start - Start the bot
• /help - Get help guide
• /about - Bot information
• /stats - Bot statistics (Admin only)

**Supported formats:** Documents, Videos, Audio, Images
**Max file size:** 2GB
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Help", callback_data="help"),
             InlineKeyboardButton("ℹ️ About", callback_data="about")],
            [InlineKeyboardButton("🔗 Support", url="https://t.me/your_channel")]
        ])
        
        await message.reply_text(
            welcome_text, 
            reply_markup=keyboard, 
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.reply_text("❌ An error occurred. Please try again.")

# Help command
@app.on_message(filters.command(["help"]))
async def help_command(client, message: Message):
    try:
        help_text = """
📖 **Help Guide**

**Basic Usage:**
Method 1 - Reply:
1. Send any file
2. Reply to that file with: `/rename new_filename`

Method 2 - Caption:
1. Send file with caption: `/rename new_filename`

**Examples:**
• `/rename my_document`
• `/rename vacation_video`
• `/rename song_audio`

**Features:**
• ✅ All file types supported
• ✅ Custom thumbnail support
• ✅ Batch renaming
• ✅ File size up to 2GB
• ✅ Fast processing

**Note:** File extension is automatically preserved.
        """
        
        await message.reply_text(help_text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in help command: {e}")

# About command
@app.on_message(filters.command(["about"]))
async def about_command(client, message: Message):
    try:
        about_text = """
ℹ️ **About This Bot**

**File Rename Bot**
A powerful Telegram bot for renaming files with ease.

**Features:**
• Fast file processing
• Support for all file types
• Custom thumbnail support
• User-friendly interface
• No quality loss

**Technical Details:**
• Framework: Pyrogram
• Language: Python 3.8+
• Database: SQLite

**Developer:** @YourUsername
**Version:** 2.0.0
        """
        
        await message.reply_text(about_text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in about command: {e}")

# Stats command (Admin only)
@app.on_message(filters.command(["stats"]))
async def stats_command(client, message: Message):
    try:
        user_id = message.from_user.id
        
        # Add your user ID here for admin access
        if user_id != 123456789:  # Replace with your user ID
            await message.reply_text("❌ This command is for admins only.")
            return
        
        total_users = await db.get_total_users()
        total_files = await db.get_total_files()
        
        stats_text = f"""
📊 **Bot Statistics**

**Users:** {total_users}
**Files Processed:** {total_files}
**Uptime:** Since {datetime.now().strftime('%Y-%m-%d')}
**Status:** ✅ Running
        """
        
        await message.reply_text(stats_text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in stats command: {e}")

# Rename command handler
@app.on_message(filters.command(["rename"]))
async def rename_command(client, message: Message):
    try:
        # Check if it's a reply to a file
        if message.reply_to_message and (message.reply_to_message.document or 
                                       message.reply_to_message.video or 
                                       message.reply_to_message.audio or 
                                       message.reply_to_message.photo):
            
            target_message = message.reply_to_message
            user_id = message.from_user.id
            
            # Extract new filename
            if len(message.command) < 2:
                await message.reply_text(
                    "❌ Please provide a new filename.\nExample: `/rename my_new_file`", 
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                return
            
            new_filename = " ".join(message.command[1:]).strip()
            await process_file_rename(client, message, target_message, user_id, new_filename)
            
        else:
            await message.reply_text("❌ Please reply to a file message with /rename command.")
            
    except Exception as e:
        logger.error(f"Error in rename command: {e}")
        await message.reply_text("❌ An error occurred while processing your request.")

# Handle files with caption
@app.on_message(filters.media & filters.caption)
async def handle_caption_files(client, message: Message):
    try:
        if message.caption and message.caption.startswith("/rename"):
            user_id = message.from_user.id
            
            # Extract new filename from caption
            parts = message.caption.split(" ", 1)
            if len(parts) < 2:
                await message.reply_text(
                    "❌ Please provide a new filename.\nExample: `/rename my_new_file`", 
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                return
            
            new_filename = parts[1].strip()
            await process_file_rename(client, message, message, user_id, new_filename)
            
    except Exception as e:
        logger.error(f"Error handling caption file: {e}")

# Main file processing function
async def process_file_rename(client, original_message, file_message, user_id, new_filename):
    processing_msg = None
    download_path = None
    new_file_path = None
    
    try:
        # Check if downloads directory exists
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        # Send initial processing message
        processing_msg = await original_message.reply_text("🔄 Processing your file...")
        
        # Get file information
        if file_message.document:
            file = file_message.document
            file_type = "document"
        elif file_message.video:
            file = file_message.video
            file_type = "video"
        elif file_message.audio:
            file = file_message.audio
            file_type = "audio"
        elif file_message.photo:
            file = file_message.photo
            file_type = "photo"
        else:
            await processing_msg.edit_text("❌ Unsupported file type.")
            return
        
        # Check file size
        file_size = file.file_size
        if file_size > MAX_FILE_SIZE:
            await processing_msg.edit_text(f"❌ File too large. Max size: {get_human_size(MAX_FILE_SIZE)}")
            return
        
        # Get original file name and extension
        if hasattr(file, 'file_name') and file.file_name:
            original_name = file.file_name
            _, file_extension = os.path.splitext(original_name)
        else:
            # Generate extension based on file type
            if file_type == "video":
                file_extension = ".mp4"
            elif file_type == "audio":
                file_extension = ".mp3"
            elif file_type == "photo":
                file_extension = ".jpg"
            else:
                file_extension = ""
            original_name = f"file{file_extension}"
        
        # Ensure new filename has extension
        if not os.path.splitext(new_filename)[1]:
            new_filename += file_extension
        
        # Download file
        await processing_msg.edit_text("📥 Downloading file...")
        
        # Use error handler for download
        download_path = await handle_error(
            file_message.download, 
            file_name=f"downloads/{user_id}_{original_name}"
        )
        
        if not download_path:
            await processing_msg.edit_text("❌ Failed to download file.")
            return
        
        # Rename file
        new_file_path = f"downloads/{user_id}_{new_filename}"
        os.rename(download_path, new_file_path)
        
        # Update database
        await db.add_file_processed(user_id, original_name, new_filename, file_size)
        
        # Prepare file for sending
        caption = f"**✅ File Renamed Successfully**\n\n**Original:** `{original_name}`\n**New Name:** `{new_filename}`\n**Size:** {get_human_size(file_size)}"
        
        # Send renamed file
        await processing_msg.edit_text("📤 Uploading renamed file...")
        
        # Send based on file type with error handling
        if file_type == "document":
            result = await handle_error(
                original_message.reply_document,
                document=new_file_path,
                caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        elif file_type == "video":
            result = await handle_error(
                original_message.reply_video,
                video=new_file_path,
                caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        elif file_type == "audio":
            result = await handle_error(
                original_message.reply_audio,
                audio=new_file_path,
                caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        elif file_type == "photo":
            result = await handle_error(
                original_message.reply_photo,
                photo=new_file_path,
                caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        
        if not result:
            await processing_msg.edit_text("❌ Failed to upload renamed file.")
            return
        
        # Clean up
        if processing_msg:
            await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        try:
            if processing_msg:
                await processing_msg.edit_text("❌ An error occurred while processing your file.")
            else:
                await original_message.reply_text("❌ An error occurred while processing your file.")
        except Exception as edit_error:
            logger.error(f"Error editing message: {edit_error}")
        
    finally:
        # Clean up downloaded files
        try:
            if download_path and os.path.exists(download_path):
                os.remove(download_path)
            if new_file_path and os.path.exists(new_file_path):
                os.remove(new_file_path)
        except Exception as clean_error:
            logger.error(f"Error cleaning files: {clean_error}")

# Callback query handler
@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data == "help":
            help_text = """
📖 **Quick Help**

**To rename a file:**
1. Send any file to me
2. Reply with `/rename new_name`

**Or use caption:**
Send file with caption: `/rename new_name`

**Examples:**
• `/rename my_document`
• `/rename vacation_video.mp4`
• `/rename song_audio`

The bot will automatically preserve the file extension.
            """
            await callback_query.message.edit_text(help_text, parse_mode=enums.ParseMode.MARKDOWN)
            
        elif data == "about":
            about_text = """
🤖 **File Rename Bot**

A simple and efficient bot for renaming files on Telegram.

**Features:**
• All file types supported
• Fast processing
• No quality loss
• Easy to use

**Developer:** @YourUsername
            """
            await callback_query.message.edit_text(about_text, parse_mode=enums.ParseMode.MARKDOWN)
        
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")

# Startup event
@app.on_message(filters.command("start"))
async def startup_handler(client, message: Message):
    # This will trigger when bot starts and receives first start command
    pass

# Initialize bot
async def initialize_bot():
    """Initialize bot components"""
    try:
        await db.create_tables()
        await clean_downloads()
        logger.info("Bot initialized successfully!")
    except Exception as e:
        logger.error(f"Error initializing bot: {e}")

if __name__ == "__main__":
    print("🤖 Starting File Rename Bot...")
    
    # Run initialization and start bot
    async def main():
        await initialize_bot()
        await app.start()
        print("✅ Bot started successfully!")
        await asyncio.Event().wait()  # Run forever
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Cleanup on exit
        try:
            asyncio.run(app.stop())
            asyncio.run(clean_downloads())
        except:
            pass
