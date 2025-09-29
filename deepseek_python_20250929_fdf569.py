import os
import asyncio
import logging
import sys
import aiohttp
import aiofiles
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait, RPCError, SessionPasswordNeeded
import json
import time
from datetime import datetime
import concurrent.futures
import hashlib
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMIN", "").split() if admin_id.strip()]

# Validate required environment variables
if not BOT_TOKEN or not API_ID or not API_HASH:
    print("❌ Error: BOT_TOKEN, API_ID, and API_HASH must be set in .env file")
    sys.exit(1)

# Enhanced settings for 4GB file handling
MAX_WORKERS = 15
CHUNK_SIZE = 16 * 1024 * 1024
DOWNLOAD_THREADS = 12
UPLOAD_THREADS = 10
BUFFER_SIZE = 128 * 1024
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"
STATS_DB = "stats.json"

# Ensure storage directories exist
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)
os.makedirs("temp", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("large_files", exist_ok=True)

# Initialize JSON files
def initialize_json_files():
    """Initialize all JSON files with default structure"""
    files_to_create = {
        USER_DB: {
            "example": {
                "joined_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "files_processed": 0,
                "total_data_processed": 0
            }
        },
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        STATS_DB: {
            datetime.now().strftime("%Y-%m-%d"): {
                "files_processed": 0,
                "bytes_processed": 0,
                "users_active": [],
                "large_files_processed": 0
            }
        }
    }
    
    for file_path, default_data in files_to_create.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Created {file_path}")

# Initialize files
initialize_json_files()

# Thread pool
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Helper functions
def load_json(file_path):
    """Load JSON file with error handling"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # Return empty dict if file is corrupted or doesn't exist
        return {}

def save_json(file_path, data):
    """Save data to JSON file with error handling"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

def save_user(user_id):
    """Save or update user data"""
    users = load_json(USER_DB)
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {
            "joined_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "files_processed": 0,
            "total_data_processed": 0
        }
        save_json(USER_DB, users)

def update_user_activity(user_id, files_processed=0, data_processed=0):
    """Update user activity and statistics"""
    users = load_json(USER_DB)
    user_id_str = str(user_id)
    
    if user_id_str in users:
        users[user_id_str]["last_active"] = datetime.now().isoformat()
        if files_processed > 0:
            users[user_id_str]["files_processed"] = users[user_id_str].get("files_processed", 0) + files_processed
        if data_processed > 0:
            users[user_id_str]["total_data_processed"] = users[user_id_str].get("total_data_processed", 0) + data_processed
        save_json(USER_DB, users)

def update_stats(files_processed=0, bytes_processed=0, large_file=False):
    """Update bot statistics"""
    stats = load_json(STATS_DB)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in stats:
        stats[today] = {
            "files_processed": 0,
            "bytes_processed": 0,
            "users_active": [],
            "large_files_processed": 0
        }
    
    if files_processed > 0:
        stats[today]["files_processed"] += files_processed
    if bytes_processed > 0:
        stats[today]["bytes_processed"] += bytes_processed
    if large_file:
        stats[today]["large_files_processed"] = stats[today].get("large_files_processed", 0) + 1
    
    save_json(STATS_DB, stats)

def admin_only(func):
    async def wrapper(client, message):
        if message.from_user.id not in ADMINS:
            await message.reply("🚫 **Access Denied!** This command is for admins only.")
            return
        return await func(client, message)
    return wrapper

def format_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def format_duration(seconds):
    """Convert seconds to readable time format"""
    if not seconds:
        return "00:00"
    minutes = seconds // 60
    seconds = seconds % 60
    hours = minutes // 60
    minutes = minutes % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def get_uptime():
    """Get bot uptime"""
    uptime_seconds = int(time.time() - bot_start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

def is_large_file(file_size):
    """Check if file is considered large"""
    return file_size > (100 * 1024 * 1024)  # 100MB+

# Message tracking to prevent duplicates
def is_message_processed(message_id):
    return message_id in processed_messages

def mark_message_processed(message_id):
    processed_messages.add(message_id)
    if len(processed_messages) > 2000:
        processed_messages.clear()

def is_user_processing(user_id):
    return user_processing.get(user_id, False)

def set_user_processing(user_id, status):
    user_processing[user_id] = status

# Initialize Pyrogram Client with proper session handling
try:
    app = Client(
        "file_rename_bot_turbo_pro",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=30,
        workers=300,
        max_concurrent_transmissions=15,
        in_memory=False
    )
    print("✅ Pyrogram client initialized successfully")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    save_user(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Turbo Status", callback_data="turbo_status")],
        [InlineKeyboardButton("📊 Bot Help", callback_data="bot_help")],
        [InlineKeyboardButton("💾 File Limits", callback_data="file_limits")]
    ])
    
    await message.reply_text(
        "🚀 **ULTRA TURBO PRO MODE ACTIVATED!**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        "I'm now running in **ULTRA TURBO PRO MODE** with:\n"
        "• ⚡ Support for files up to **4GB**\n"
        "• 🚀 Parallel chunked downloads/uploads\n"
        "• 💨 Optimized for large file processing\n"
        "• 🔥 Maximum speed and efficiency\n\n"
        "**Available Commands:**\n"
        "• `/view_thumb` - View your thumbnail\n"
        "• `/del_thumb` - Delete your thumbnail\n"
        "• `/set_caption` - Set custom caption\n"
        "• `/see_caption` - View your caption\n"
        "• `/del_caption` - Delete custom caption\n"
        "• `/turbo_status` - Check bot performance\n"
        "• `/file_limits` - Check file size limits\n"
        "• `/status` - Bot status (Admin)\n"
        "• `/broadcast` - Broadcast message (Admin)\n"
        "• `/restart` - Restart bot (Admin)\n\n"
        "**To rename a file:**\n"
        "Reply to any file with `/rename new_filename.ext`\n\n"
        "**⚡ NOW WITH 4GB FILE SUPPORT! ⚡**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# File limits command
@app.on_message(filters.command("file_limits"))
async def file_limits_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    await message.reply_text(
        "📁 **File Size Limits & Support**\n\n"
        "✅ **Supported File Types:**\n"
        "• Documents (PDF, ZIP, RAR, etc.)\n"
        "• Videos (MP4, MKV, AVI, etc.)\n"
        "• Audio (MP3, FLAC, WAV, etc.)\n"
        "• Images (JPG, PNG, etc.)\n\n"
        "📊 **Size Limits:**\n"
        f"• **Maximum File Size:** {format_size(MAX_FILE_SIZE)}\n"
        "• **Recommended:** Up to 2GB for best performance\n"
        "• **Large Files:** 2GB-4GB (slower processing)\n\n"
        "⚡ **Processing Speed:**\n"
        "• Small files (<100MB): Ultra Fast\n"
        "• Medium files (100MB-1GB): Fast\n"
        "• Large files (1GB-4GB): Moderate\n\n"
        "**Note:** Very large files may take several minutes to process.",
        parse_mode=ParseMode.MARKDOWN
    )

# View thumbnail command
@app.on_message(filters.command("view_thumb"))
async def view_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnail_file = thumbnails.get(str(user_id))
    
    if thumbnail_file and os.path.exists(thumbnail_file):
        await message.reply_photo(thumbnail_file, caption="📸 **Your Current Thumbnail**")
    else:
        await message.reply_text("❌ **No thumbnail found!**\nSend an image as photo to set thumbnail.")

# Set thumbnail from photo
@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumb_path = f"thumbnails/{user_id}_{int(time.time())}.jpg"
    
    status_msg = await message.reply_text("🚀 **Downloading thumbnail...**")
    try:
        await message.download(thumb_path)
        
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        
        await status_msg.edit_text("✅ **Thumbnail set successfully!**")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error setting thumbnail:** {str(e)}")

# Set caption command
@app.on_message(filters.command("set_caption"))
async def set_caption_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/set_caption Your custom caption here`\n\n"
            "**Available variables:**\n"
            "• `{filename}` - Original file name\n"
            "• `{size}` - File size\n"
            "• `{duration}` - Duration (for media files)\n"
            "• `{width}x{height}` - Resolution (for media files)\n\n"
            "**Example:**\n`/set_caption 📁 {filename} | Size: {size} | Turbo Powered 🚀`"
        )
        return
    
    custom_caption = " ".join(message.command[1:])
    
    captions = load_json(CAPTION_DB)
    captions[str(user_id)] = custom_caption
    save_json(CAPTION_DB, captions)
    
    await message.reply_text("✅ **Custom caption set successfully!**")

# View caption command
@app.on_message(filters.command("see_caption"))
async def see_caption(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    captions = load_json(CAPTION_DB)
    user_caption = captions.get(str(user_id))
    
    if user_caption:
        await message.reply_text(
            f"**Your Custom Caption:**\n\n`{user_caption}`\n\n"
            "Use `/del_caption` to remove this caption."
        )
    else:
        await message.reply_text("❌ **No custom caption set!**\nUse `/set_caption` to set one.")

# Delete caption command
@app.on_message(filters.command("del_caption"))
async def delete_caption(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    captions = load_json(CAPTION_DB)
    
    if str(user_id) in captions:
        del captions[str(user_id)]
        save_json(CAPTION_DB, captions)
        await message.reply_text("✅ **Custom caption deleted successfully!**")
    else:
        await message.reply_text("❌ **No custom caption found to delete!**")

# Enhanced file processing
async def enhanced_process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    status_msg = None
    download_path = None
    
    try:
        # Extract new file name
        if message.text:
            parts = message.text.split(" ", 1)
        else:
            parts = message.caption.split(" ", 1)
            
        if len(parts) < 2:
            await message.reply_text("❌ **Please provide a new file name!**\nExample: `/rename my_file.pdf`")
            return
        
        new_name = parts[1].strip()
        
        # Validate file name
        if not new_name or len(new_name) > 255:
            await message.reply_text("❌ **Invalid file name!** File name must be between 1-255 characters.")
            return
        
        # Check file size
        file_size = 0
        if target_message.document:
            file_size = target_message.document.file_size
        elif target_message.video:
            file_size = target_message.video.file_size
        elif target_message.audio:
            file_size = target_message.audio.file_size
        
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ **File too large!**\n\n"
                f"File size: {format_size(file_size)}\n"
                f"Maximum allowed: {format_size(MAX_FILE_SIZE)}\n\n"
                "Please try with a smaller file."
            )
            return
        
        # Start processing
        start_time = time.time()
        is_large = is_large_file(file_size)
        
        status_msg = await message.reply_text(
            f"🚀 **PROCESSING {'LARGE FILE' if is_large else 'FILE'}**\n\n"
            f"📁 **File:** {new_name}\n"
            f"📦 **Size:** {format_size(file_size)}\n"
            "⚡ **Starting download...**"
        )
        
        # Download file
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        download_path = await client.download_media(target_message, file_name=file_path)
        
        if not download_path:
            await status_msg.edit_text("❌ **Download failed!**")
            return
        
        actual_file_size = os.path.getsize(download_path)
        
        await status_msg.edit_text(
            f"✅ **DOWNLOAD COMPLETE!**\n\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"🚀 **Starting upload...**"
        )
        
        # Prepare caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Turbo Powered Upload** 🚀")
        
        # Get thumbnail
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Upload file
        if target_message.document:
            await client.send_document(
                chat_id=target_message.chat.id,
                document=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif target_message.video:
            await client.send_video(
                chat_id=target_message.chat.id,
                video=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True
            )
        elif target_message.audio:
            await client.send_audio(
                chat_id=target_message.chat.id,
                audio=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Update stats
        update_user_activity(user_id, files_processed=1, data_processed=actual_file_size)
        update_stats(files_processed=1, bytes_processed=actual_file_size, large_file=is_large)
        
        total_time = time.time() - start_time
        
        await status_msg.edit_text(
            f"🎉 **FILE RENAMED SUCCESSFULLY!** 🎉\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"⏱ **Time:** {format_duration(int(total_time))}\n\n"
            f"**Status:** COMPLETED ✅"
        )
        
    except Exception as e:
        error_msg = f"❌ **Processing Error:** {str(e)}"
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
    
    finally:
        # Cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass

# Rename command
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if is_user_processing(user_id):
        await message.reply_text("⏳ **Please wait!** You're already processing a file.")
        return
    
    if not message.reply_to_message:
        await message.reply_text(
            "**Usage:** Reply to a file with `/rename new_filename.ext`\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}"
        )
        return
    
    replied_message = message.reply_to_message
    
    if not replied_message.media:
        await message.reply_text("❌ **Please reply to a file**")
        return
    
    set_user_processing(user_id, True)
    
    try:
        await enhanced_process_file_rename(client, message, replied_message)
    finally:
        set_user_processing(user_id, False)

# Turbo status command
@app.on_message(filters.command("turbo_status"))
async def turbo_status(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    users = load_json(USER_DB)
    total_users = len(users)
    
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    
    stats = load_json(STATS_DB)
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = stats.get(today, {"files_processed": 0, "bytes_processed": 0})
    
    await message.reply_text(
        f"🚀 **TURBO BOT STATUS**\n\n"
        f"• 👥 **Total Users:** {total_users}\n"
        f"• 💾 **Memory Usage:** {memory_usage:.2f} MB\n"
        f"• 📊 **Files Today:** {today_stats['files_processed']}\n"
        f"• 💽 **Data Today:** {format_size(today_stats['bytes_processed'])}\n"
        f"• 🚀 **Max File Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"• 🕒 **Uptime:** {get_uptime()}\n\n"
        f"**Status:** ACTIVE ✅",
        parse_mode=ParseMode.MARKDOWN
    )

# Callback query handlers
@app.on_callback_query(filters.regex("turbo_status"))
async def turbo_status_callback(client, callback_query):
    await callback_query.answer()
    await turbo_status(client, callback_query.message)

@app.on_callback_query(filters.regex("bot_help"))
async def bot_help_callback(client, callback_query):
    await callback_query.answer()
    await message.reply_text(
        "**🤖 Bot Help**\n\n"
        "**Commands:**\n"
        "• `/start` - Start the bot\n"
        "• `/rename` - Rename files\n"
        "• `/set_caption` - Set custom caption\n"
        "• `/view_thumb` - View thumbnail\n"
        "• `/turbo_status` - Check status\n"
        "• `/file_limits` - File size limits\n\n"
        "**Support:** Up to 4GB files"
    )

@app.on_callback_query(filters.regex("file_limits"))
async def file_limits_callback(client, callback_query):
    await callback_query.answer()
    await file_limits_command(client, callback_query.message)

# Start the bot
if __name__ == "__main__":
    print("🚀 STARTING TURBO BOT...")
    print(f"📁 Max File Size: {format_size(MAX_FILE_SIZE)}")
    print("📊 JSON files initialized")
    print("🌐 Starting bot...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Bot startup error: {e}")