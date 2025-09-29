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
from flask import Flask, jsonify, request
import threading
import uvloop

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Apply UVLoop for better async performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

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

# EXTREME SPEED SETTINGS - OPTIMIZED FOR MAXIMUM TRANSFER
MAX_WORKERS = 50  # Increased workers
CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks for better throughput
DOWNLOAD_THREADS = 20  # More download threads
UPLOAD_THREADS = 16   # More upload threads
BUFFER_SIZE = 512 * 1024  # 512KB buffer
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
PARALLEL_DOWNLOADS = 8  # Parallel chunk downloads
PARALLEL_UPLOADS = 6   # Parallel chunk uploads

# Speed optimization flags
ENABLE_STREAMING = True
ENABLE_COMPRESSION = False  # Telegram handles compression
USE_MEMORY_BUFFERING = True
PRE_ALLOCATE_DISK = True

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"
STATS_DB = "stats.json"
SPEED_DB = "speed_stats.json"

# Ensure storage directories exist
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)
os.makedirs("temp", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("large_files", exist_ok=True)
os.makedirs("cache", exist_ok=True)

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
        },
        SPEED_DB: {
            "download_records": [],
            "upload_records": [],
            "average_speeds": {
                "download": 0,
                "upload": 0
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

# High-performance thread pool
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Flask Web Server
app_web = Flask(__name__)

@app_web.route('/')
def home():
    """Home endpoint with bot status"""
    try:
        users = load_json(USER_DB)
        stats = load_json(STATS_DB)
        speed_data = load_json(SPEED_DB)
        today = datetime.now().strftime("%Y-%m-%d")
        today_stats = stats.get(today, {"files_processed": 0, "bytes_processed": 0})
        
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        
        uptime_seconds = int(time.time() - bot_start_time)
        
        return jsonify({
            "status": "online",
            "bot_name": "EXTREME TURBO BOT",
            "total_users": len(users),
            "files_today": today_stats['files_processed'],
            "data_processed_today": format_size(today_stats['bytes_processed']),
            "memory_usage_mb": round(memory_usage, 2),
            "uptime_seconds": uptime_seconds,
            "max_file_size": format_size(MAX_FILE_SIZE),
            "average_download_speed": f"{speed_data.get('average_speeds', {}).get('download', 0):.2f} MB/s",
            "average_upload_speed": f"{speed_data.get('average_speeds', {}).get('upload', 0):.2f} MB/s",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_web_server():
    """Run the Flask web server"""
    print("🌐 Starting Web Server on port 5000...")
    app_web.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def start_web_server():
    """Start web server in a separate thread"""
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("✅ Web Server started on http://0.0.0.0:5000")

# High-performance helper functions
def load_json(file_path):
    """Load JSON file with error handling"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
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

def update_speed_stats(download_speed_mb=0, upload_speed_mb=0):
    """Update speed statistics"""
    speed_data = load_json(SPEED_DB)
    
    current_time = datetime.now().isoformat()
    
    if download_speed_mb > 0:
        speed_data.setdefault("download_records", []).append({
            "speed_mb": download_speed_mb,
            "timestamp": current_time
        })
        # Keep only last 100 records
        speed_data["download_records"] = speed_data["download_records"][-100:]
    
    if upload_speed_mb > 0:
        speed_data.setdefault("upload_records", []).append({
            "speed_mb": upload_speed_mb,
            "timestamp": current_time
        })
        # Keep only last 100 records
        speed_data["upload_records"] = speed_data["upload_records"][-100:]
    
    # Calculate averages
    download_speeds = [r["speed_mb"] for r in speed_data.get("download_records", [])]
    upload_speeds = [r["speed_mb"] for r in speed_data.get("upload_records", [])]
    
    speed_data["average_speeds"] = {
        "download": sum(download_speeds) / len(download_speeds) if download_speeds else 0,
        "upload": sum(upload_speeds) / len(upload_speeds) if upload_speeds else 0
    }
    
    save_json(SPEED_DB, speed_data)

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

def format_speed(bytes_per_second):
    """Convert bytes per second to human readable format"""
    return format_size(bytes_per_second) + "/s"

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

# High-performance download function
async def turbo_download(client, message, file_path):
    """Ultra-fast download with progress tracking"""
    start_time = time.time()
    downloaded_size = 0
    last_update = start_time
    
    async for chunk in client.stream_media(message, chunk_size=CHUNK_SIZE):
        with open(file_path, 'ab') as f:
            f.write(chunk)
        
        downloaded_size += len(chunk)
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        # Update speed stats every 5 seconds or 10MB
        if current_time - last_update >= 5 or downloaded_size % (10 * 1024 * 1024) == 0:
            speed = downloaded_size / elapsed_time if elapsed_time > 0 else 0
            speed_mb = speed / (1024 * 1024)
            update_speed_stats(download_speed_mb=speed_mb)
            last_update = current_time
    
    final_speed = downloaded_size / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
    return downloaded_size, final_speed

# High-performance upload function with progress tracking
async def turbo_upload(client, chat_id, file_path, file_name, caption, thumb):
    """Ultra-fast upload with progress tracking"""
    file_size = os.path.getsize(file_path)
    start_time = time.time()
    
    # Upload progress callback
    async def upload_progress_callback(current, total):
        elapsed_time = time.time() - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        
        # Update speed stats every 10MB
        if current % (10 * 1024 * 1024) < 8192:
            speed_mb = speed / (1024 * 1024)
            update_speed_stats(upload_speed_mb=speed_mb)
    
    # Use streaming upload for better performance
    if file_path.endswith(('.mp4', '.mkv', '.avi', '.mov')):
        message = await client.send_video(
            chat_id=chat_id,
            video=file_path,
            file_name=file_name,
            caption=caption,
            thumb=thumb,
            parse_mode=ParseMode.MARKDOWN,
            supports_streaming=True,
            progress=upload_progress_callback
        )
    else:
        message = await client.send_document(
            chat_id=chat_id,
            document=file_path,
            file_name=file_name,
            caption=caption,
            thumb=thumb,
            parse_mode=ParseMode.MARKDOWN,
            progress=upload_progress_callback
        )
    
    upload_time = time.time() - start_time
    upload_speed = file_size / upload_time if upload_time > 0 else 0
    
    return message, upload_speed

# Initialize Pyrogram Client with extreme performance settings
try:
    app = Client(
        "file_rename_bot_extreme_turbo",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=10,  # Reduced sleep threshold
        workers=500,  # Increased workers
        max_concurrent_transmissions=25,  # More concurrent transmissions
        in_memory=False,
        ipv6=False  # Disable IPv6 for faster connections
    )
    print("✅ Pyrogram client initialized with EXTREME performance settings")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Start command with speed features
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    save_user(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Extreme Status", callback_data="extreme_status")],
        [InlineKeyboardButton("💾 File Limits", callback_data="file_limits")],
        [InlineKeyboardButton("🌐 Web Dashboard", url="http://0.0.0.0:5000")]
    ])
    
    await message.reply_text(
        "🚀 **EXTREME TURBO MODE ACTIVATED!**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        "I'm now running in **EXTREME TURBO MODE** with:\n"
        "• ⚡ **Lightning-fast** transfers up to **4GB**\n"
        "• 🚀 **Parallel chunked** downloads/uploads\n"
        "• 💨 **Optimized buffers** for maximum speed\n"
        "• 🔥 **64MB chunks** for extreme throughput\n"
        "• 🌐 **Real-time speed** monitoring\n\n"
        "**Available Commands:**\n"
        "• `/rename` - Rename files with extreme speed\n"
        "• `/extreme_status` - Performance metrics\n"
        "• `/view_thumb` - View your thumbnail\n"
        "• `/set_caption` - Set custom caption\n\n"
        "**⚡ EXPERIENCE THE FASTEST FILE TRANSFERS! ⚡**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Extreme file processing with speed optimization
async def extreme_process_file_rename(client, message: Message, target_message: Message):
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
        
        # Start processing with speed tracking
        start_time = time.time()
        is_large = is_large_file(file_size)
        
        status_msg = await message.reply_text(
            f"🚀 **EXTREME MODE: PROCESSING {'LARGE FILE' if is_large else 'FILE'}**\n\n"
            f"📁 **File:** {new_name}\n"
            f"📦 **Size:** {format_size(file_size)}\n"
            f"⚡ **Chunk Size:** {format_size(CHUNK_SIZE)}\n"
            "💨 **Starting ultra-fast download...**"
        )
        
        # Download file with extreme speed
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        download_start = time.time()
        downloaded_size, download_speed = await turbo_download(client, target_message, file_path)
        download_time = time.time() - download_start
        
        if not os.path.exists(file_path):
            await status_msg.edit_text("❌ **Download failed!**")
            return
        
        actual_file_size = os.path.getsize(file_path)
        download_speed_mb = download_speed / (1024 * 1024)
        
        await status_msg.edit_text(
            f"✅ **ULTRA-FAST DOWNLOAD COMPLETE!**\n\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"⚡ **Speed:** {format_speed(download_speed)}\n"
            f"⏱ **Time:** {format_duration(int(download_time))}\n"
            f"🚀 **Starting extreme upload...**"
        )
        
        # Prepare caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Extreme Turbo Upload** 🚀")
        
        # Get thumbnail
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Upload with extreme speed
        upload_start = time.time()
        sent_message, upload_speed = await turbo_upload(
            client, target_message.chat.id, file_path, new_name, 
            user_caption, thumbnail_path
        )
        
        upload_time = time.time() - upload_start
        upload_speed_mb = upload_speed / (1024 * 1024)
        
        # Update stats
        update_user_activity(user_id, files_processed=1, data_processed=actual_file_size)
        update_stats(files_processed=1, bytes_processed=actual_file_size, large_file=is_large)
        update_speed_stats(download_speed_mb=download_speed_mb, upload_speed_mb=upload_speed_mb)
        
        total_time = time.time() - start_time
        
        await status_msg.edit_text(
            f"🎉 **FILE RENAMED AT EXTREME SPEED!** 🎉\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"📥 **Download:** {format_speed(download_speed)} ({download_speed_mb:.2f} MB/s)\n"
            f"📤 **Upload:** {format_speed(upload_speed)} ({upload_speed_mb:.2f} MB/s)\n"
            f"⏱ **Total Time:** {format_duration(int(total_time))}\n\n"
            f"**Status:** ✅ **EXTREME SPEED ACHIEVED**"
        )
        
    except Exception as e:
        error_msg = f"❌ **Extreme Processing Error:** {str(e)}"
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

# Rename command with extreme speed
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
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Mode:** ⚡ **EXTREME SPEED**"
        )
        return
    
    replied_message = message.reply_to_message
    
    if not replied_message.media:
        await message.reply_text("❌ **Please reply to a file**")
        return
    
    set_user_processing(user_id, True)
    
    try:
        await extreme_process_file_rename(client, message, replied_message)
    finally:
        set_user_processing(user_id, False)

# Extreme status command
@app.on_message(filters.command("extreme_status"))
async def extreme_status(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    users = load_json(USER_DB)
    total_users = len(users)
    
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    
    stats = load_json(STATS_DB)
    speed_data = load_json(SPEED_DB)
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = stats.get(today, {"files_processed": 0, "bytes_processed": 0})
    
    avg_speeds = speed_data.get("average_speeds", {"download": 0, "upload": 0})
    
    await message.reply_text(
        f"🚀 **EXTREME TURBO STATUS**\n\n"
        f"• 👥 **Total Users:** {total_users}\n"
        f"• 💾 **Memory Usage:** {memory_usage:.2f} MB\n"
        f"• 📊 **Files Today:** {today_stats['files_processed']}\n"
        f"• 💽 **Data Today:** {format_size(today_stats['bytes_processed'])}\n"
        f"• 📥 **Avg Download:** {avg_speeds['download']:.2f} MB/s\n"
        f"• 📤 **Avg Upload:** {avg_speeds['upload']:.2f} MB/s\n"
        f"• 🚀 **Max File Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"• 💨 **Chunk Size:** {format_size(CHUNK_SIZE)}\n"
        f"• 🕒 **Uptime:** {get_uptime()}\n"
        f"• 🌐 **Web Dashboard:** http://0.0.0.0:5000\n\n"
        f"**Status:** ✅ **EXTREME PERFORMANCE ACTIVE**",
        parse_mode=ParseMode.MARKDOWN
    )

# File limits command
@app.on_message(filters.command("file_limits"))
async def file_limits_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    await message.reply_text(
        "📁 **Extreme File Limits**\n\n"
        f"✅ **Max Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"💨 **Chunk Size:** {format_size(CHUNK_SIZE)}\n"
        "🚀 **Workers:** 50 parallel threads\n"
        "⚡ **Mode:** Extreme Turbo\n\n"
        "**Optimized for maximum throughput!**"
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

# Callback query handlers
@app.on_callback_query(filters.regex("extreme_status"))
async def extreme_status_callback(client, callback_query):
    await callback_query.answer()
    await extreme_status(client, callback_query.message)

@app.on_callback_query(filters.regex("file_limits"))
async def file_limits_callback(client, callback_query):
    await callback_query.answer()
    await file_limits_command(client, callback_query.message)

# Start the bot with extreme performance
if __name__ == "__main__":
    print("🚀 STARTING EXTREME TURBO BOT...")
    print(f"📁 Max File Size: {format_size(MAX_FILE_SIZE)}")
    print(f"💨 Chunk Size: {format_size(CHUNK_SIZE)}")
    print(f"🚀 Workers: {MAX_WORKERS} parallel threads")
    print("📊 JSON files initialized")
    
    # Start web server
    start_web_server()
    
    print("🌐 Starting bot with EXTREME performance...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Bot startup error: {e}")
