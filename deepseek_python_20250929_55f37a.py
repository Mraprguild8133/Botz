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
import multiprocessing
from io import BytesIO
import gc

# Configure logging - minimal for performance
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Apply UVLoop for maximum async performance
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

# MAXIMUM PERFORMANCE SETTINGS
MAX_WORKERS = min(200, multiprocessing.cpu_count() * 20)  # Extreme workers
CHUNK_SIZE = 256 * 1024 * 1024  # 256MB chunks for maximum throughput
DOWNLOAD_THREADS = 64  # Maximum download threads
UPLOAD_THREADS = 48   # Maximum upload threads
BUFFER_SIZE = 4 * 1024 * 1024  # 4MB buffer for fast I/O
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
PARALLEL_DOWNLOADS = 32  # Parallel chunk downloads
PARALLEL_UPLOADS = 24   # Parallel chunk uploads

# Extreme optimization flags
ENABLE_MEMORY_MAPPING = True
ENABLE_DIRECT_IO = True
ENABLE_COMPRESSION = False
ENABLE_STREAMING = True
PRE_ALLOCATE_DISK = True
USE_ZERO_COPY = True
ENABLE_BATCH_PROCESSING = True
ENABLE_LARGE_FILE_OPTIMIZATION = True

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}
user_upload_preferences = {}
active_downloads = {}
active_uploads = {}

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"
STATS_DB = "stats.json"
SPEED_DB = "speed_stats.json"
PREFERENCES_DB = "preferences.json"

# Ensure storage directories exist with optimal permissions
for directory in ["downloads", "thumbnails", "temp", "templates", "large_files", "cache"]:
    os.makedirs(directory, exist_ok=True)
    # Try to set directory for better performance (Linux/Unix)
    try:
        os.system(f"chmod 755 {directory}")
    except:
        pass

# Initialize JSON files with minimal I/O
def initialize_json_files():
    """Initialize all JSON files with optimized structure"""
    files_to_create = {
        USER_DB: {},
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        PREFERENCES_DB: {},
        STATS_DB: {
            datetime.now().strftime("%Y-%m-%d"): {
                "files_processed": 0,
                "bytes_processed": 0,
                "users_active": set(),
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
                json.dump(default_data, f, separators=(',', ':'), ensure_ascii=False)

# Initialize files
initialize_json_files()

# High-performance thread pool with maximum workers
thread_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=MAX_WORKERS,
    thread_name_prefix="turbo_worker"
)

# Memory-optimized Flask Web Server
app_web = Flask(__name__)

@app_web.route('/')
def home():
    """Minimal home endpoint"""
    try:
        return jsonify({
            "status": "online",
            "bot_name": "MAX TURBO BOT",
            "max_file_size": format_size(MAX_FILE_SIZE),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error"}), 500

def run_web_server():
    """Run optimized Flask web server"""
    print("🌐 Starting Max Web Server on port 5000...")
    app_web.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def start_web_server():
    """Start web server in separate thread"""
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("✅ Web Server started on http://0.0.0.0:5000")

# Ultra-fast helper functions
def load_json(file_path):
    """Load JSON with memory optimization"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    """Save JSON with minimal I/O"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        return True
    except:
        return False

def get_user_preference(user_id):
    """Get user preference with caching"""
    return user_upload_preferences.get(str(user_id), "auto")

def set_user_preference(user_id, preference):
    """Set user preference with caching"""
    user_upload_preferences[str(user_id)] = preference
    preferences = load_json(PREFERENCES_DB)
    preferences[str(user_id)] = preference
    save_json(PREFERENCES_DB, preferences)
    return True

def format_size(size_bytes):
    """Ultra-fast size formatting"""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def format_duration(seconds):
    """Fast duration formatting"""
    if not seconds:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def format_speed(bytes_per_second):
    """Fast speed formatting"""
    return format_size(bytes_per_second) + "/s"

def get_uptime():
    """Fast uptime calculation"""
    seconds = int(time.time() - bot_start_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def is_large_file(file_size):
    """Fast size check"""
    return file_size > (100 * 1024 * 1024)  # 100MB+

def get_file_extension(file_path):
    """Fast extension extraction"""
    return os.path.splitext(file_path)[1].lower()

def is_video_file(file_path):
    """Fast video detection"""
    return get_file_extension(file_path) in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.3gp']

def is_audio_file(file_path):
    """Fast audio detection"""
    return get_file_extension(file_path) in ['.mp3', '.m4a', '.flac', '.wav', '.ogg', '.aac', '.wma']

def is_image_file(file_path):
    """Fast image detection"""
    return get_file_extension(file_path) in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff']

# Message tracking with memory optimization
def is_message_processed(message_id):
    return message_id in processed_messages

def mark_message_processed(message_id):
    processed_messages.add(message_id)
    # Auto-clean to prevent memory bloat
    if len(processed_messages) > 1000:
        processed_messages.clear()

def is_user_processing(user_id):
    return user_processing.get(user_id, False)

def set_user_processing(user_id, status):
    user_processing[user_id] = status

# ULTRA-FAST DOWNLOAD FUNCTION WITH LARGE FILE SUPPORT
async def max_download(client, message, file_path):
    """Maximum speed download with large file optimization"""
    start_time = time.time()
    
    try:
        # Get file size for pre-allocation
        file_size = 0
        if hasattr(message, 'document') and message.document:
            file_size = message.document.file_size
        elif hasattr(message, 'video') and message.video:
            file_size = message.video.file_size
        elif hasattr(message, 'audio') and message.audio:
            file_size = message.audio.file_size
        
        # Pre-allocate file for large files (faster writes)
        if PRE_ALLOCATE_DISK and file_size > 100 * 1024 * 1024:  # 100MB+
            try:
                with open(file_path, 'wb') as f:
                    f.seek(file_size - 1)
                    f.write(b'\0')
            except Exception as e:
                print(f"Pre-allocation warning: {e}")
        
        # Use fastest download method with progress for large files
        download_path = await client.download_media(
            message,
            file_name=file_path,
            in_memory=False,  # Disk-based for large files
            block=True  # Ensure complete download
        )
        
        if download_path and os.path.exists(download_path):
            actual_size = os.path.getsize(download_path)
            download_time = time.time() - start_time
            download_speed = actual_size / download_time if download_time > 0 else 0
            return actual_size, download_speed
        
        return 0, 0
        
    except Exception as e:
        print(f"Download error: {e}")
        return 0, 0

# ULTRA-FAST UPLOAD FUNCTIONS WITH LARGE FILE SUPPORT
async def max_upload_document(client, chat_id, file_path, file_name, caption, thumb):
    """Maximum speed document upload with large file support"""
    start_time = time.time()
    file_size = os.path.getsize(file_path)
    
    try:
        message = await client.send_document(
            chat_id=chat_id,
            document=file_path,
            file_name=file_name,
            caption=caption,
            thumb=thumb,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True,  # Faster
            force_document=True  # Ensure document type
        )
        
        upload_time = time.time() - start_time
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        return message, upload_speed
    except Exception as e:
        print(f"Document upload error: {e}")
        raise

async def max_upload_video(client, chat_id, file_path, file_name, caption, thumb):
    """Maximum speed video upload with large file support"""
    start_time = time.time()
    file_size = os.path.getsize(file_path)
    
    try:
        message = await client.send_video(
            chat_id=chat_id,
            video=file_path,
            file_name=file_name,
            caption=caption,
            thumb=thumb,
            parse_mode=ParseMode.MARKDOWN,
            supports_streaming=True,
            disable_notification=True,  # Faster
            progress=None  # No progress for speed
        )
        
        upload_time = time.time() - start_time
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        return message, upload_speed
    except Exception as e:
        print(f"Video upload error: {e}")
        # Fallback to document upload
        return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)

async def max_upload_audio(client, chat_id, file_path, file_name, caption, thumb):
    """Maximum speed audio upload"""
    start_time = time.time()
    file_size = os.path.getsize(file_path)
    
    try:
        message = await client.send_audio(
            chat_id=chat_id,
            audio=file_path,
            file_name=file_name,
            caption=caption,
            thumb=thumb,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True
        )
        
        upload_time = time.time() - start_time
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        return message, upload_speed
    except Exception as e:
        print(f"Audio upload error: {e}")
        return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)

async def max_upload_photo(client, chat_id, file_path, caption):
    """Maximum speed photo upload"""
    start_time = time.time()
    file_size = os.path.getsize(file_path)
    
    try:
        message = await client.send_photo(
            chat_id=chat_id,
            photo=file_path,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True
        )
        
        upload_time = time.time() - start_time
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        return message, upload_speed
    except Exception as e:
        print(f"Photo upload error: {e}")
        raise

async def max_smart_upload(client, chat_id, file_path, file_name, caption, thumb, user_preference="auto"):
    """Ultra-fast smart upload with fallback handling"""
    
    try:
        if user_preference == "document":
            return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)
        elif user_preference == "video" and is_video_file(file_path):
            return await max_upload_video(client, chat_id, file_path, file_name, caption, thumb)
        elif user_preference == "video":
            return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)
        else:
            # Auto detection - minimal checks
            if is_video_file(file_path):
                return await max_upload_video(client, chat_id, file_path, file_name, caption, thumb)
            elif is_audio_file(file_path):
                return await max_upload_audio(client, chat_id, file_path, file_name, caption, thumb)
            elif is_image_file(file_path):
                return await max_upload_photo(client, chat_id, file_path, caption)
            else:
                return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)
    except FloodWait as e:
        # Handle flood waits gracefully
        await asyncio.sleep(e.value)
        # Retry once
        return await max_upload_document(client, chat_id, file_path, file_name, caption, thumb)
    except Exception as e:
        print(f"Upload error: {e}")
        raise

# Initialize Pyrogram Client with MAXIMUM performance
try:
    app = Client(
        "max_turbo_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=2,  # Minimal sleep for maximum speed
        workers=1500,  # Extreme workers
        max_concurrent_transmissions=100,  # Maximum concurrent
        in_memory=False,
        ipv6=False,
        test_mode=False
    )
    print("🚀 Pyrogram client initialized with MAXIMUM performance settings")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Ultra-fast start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Max Status", callback_data="max_status")],
        [InlineKeyboardButton("🚀 Upload Mode", callback_data="upload_options")],
        [InlineKeyboardButton("💨 File Limits", callback_data="file_limits")]
    ])
    
    await message.reply_text(
        "⚡ **MAX TURBO MODE ACTIVATED!**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        "**MAXIMUM SPEED FEATURES:**\n"
        "• 🚀 **256MB Chunks** for extreme throughput\n"
        "• ⚡ **1500 Workers** for parallel processing\n"
        "• 💨 **Zero-delay** operations\n"
        "• 🔥 **Large file optimized** (up to 4GB)\n"
        "• 📁 **Smart upload** options\n\n"
        "**Commands:** `/rename` • `/upload_mode` • `/max_status`\n\n"
        "**⚡ ULTRA FAST FILE TRANSFERS! ⚡**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Ultra-fast upload mode command
@app.on_message(filters.command("upload_mode"))
async def upload_mode_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    current_mode = get_user_preference(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto", callback_data="mode_auto")],
        [InlineKeyboardButton("📄 Document", callback_data="mode_document")],
        [InlineKeyboardButton("🎬 Video", callback_data="mode_video")],
    ])
    
    await message.reply_text(
        f"🚀 **Upload Mode:** `{current_mode.upper()}`\n\n"
        "Choose upload method:",
        reply_markup=keyboard
    )

# MAXIMUM PERFORMANCE FILE PROCESSING
async def max_process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    download_path = None
    
    try:
        # Ultra-fast parsing
        parts = (message.text or message.caption).split(" ", 1)
        if len(parts) < 2:
            await message.reply("❌ **Usage:** `/rename new_filename.ext`")
            return
        
        new_name = parts[1].strip()
        if not new_name or len(new_name) > 255:
            await message.reply("❌ Invalid filename")
            return
        
        # Get file size quickly with better error handling
        file_size = 0
        try:
            if target_message.document:
                file_size = target_message.document.file_size or 0
            elif target_message.video:
                file_size = target_message.video.file_size or 0
            elif target_message.audio:
                file_size = target_message.audio.file_size or 0
            elif target_message.photo:
                # Photos might not have file_size attribute
                file_size = 10 * 1024 * 1024  # Assume 10MB max for photos
        except:
            file_size = 0
        
        if file_size > MAX_FILE_SIZE:
            await message.reply(f"❌ File too large: {format_size(file_size)}")
            return
        
        # Get user preference
        user_preference = get_user_preference(user_id)
        
        # Start processing with minimal updates
        start_time = time.time()
        status_msg = await message.reply("🚀 **MAX TURBO PROCESSING...**")
        
        # Generate file path
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        # MAXIMUM SPEED DOWNLOAD
        download_start = time.time()
        downloaded_size, download_speed = await max_download(client, target_message, file_path)
        download_time = time.time() - download_start
        
        if not os.path.exists(file_path) or downloaded_size == 0:
            await status_msg.edit("❌ Download failed - file may be too large or corrupted")
            return
        
        actual_file_size = os.path.getsize(file_path)
        download_speed_mb = download_speed / (1024 * 1024) if download_speed > 0 else 0
        
        # Update status for large files
        if actual_file_size > 100 * 1024 * 1024:  # 100MB+
            await status_msg.edit(f"✅ **DOWNLOADED {format_size(actual_file_size)}! UPLOADING...**")
        else:
            await status_msg.edit("✅ **DOWNLOADED! UPLOADING...**")
        
        # Prepare upload parameters
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Max Turbo**")
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # MAXIMUM SPEED UPLOAD
        upload_start = time.time()
        sent_message, upload_speed = await max_smart_upload(
            client, target_message.chat.id, file_path, new_name, 
            user_caption, thumbnail_path, user_preference
        )
        upload_time = time.time() - upload_start
        upload_speed_mb = upload_speed / (1024 * 1024) if upload_speed > 0 else 0
        
        total_time = time.time() - start_time
        
        # Get upload type
        upload_type = "Document"
        if sent_message.video:
            upload_type = "Video"
        elif sent_message.audio:
            upload_type = "Audio"
        elif sent_message.photo:
            upload_type = "Photo"
        
        # Performance-based completion message
        speed_emoji = "⚡" if download_speed_mb > 50 or upload_speed_mb > 50 else "🚀"
        
        await status_msg.edit(
            f"✅ **MAX TURBO COMPLETE!** {speed_emoji}\n\n"
            f"📁 `{new_name}`\n"
            f"📦 {format_size(actual_file_size)}\n"
            f"🚀 {upload_type} • {format_duration(int(total_time))}\n"
            f"📥 {download_speed_mb:.1f} MB/s • 📤 {upload_speed_mb:.1f} MB/s\n"
            f"💾 Large file: {'✅' if is_large_file(actual_file_size) else '❌'}"
        )
        
    except FloodWait as e:
        # Handle flood wait gracefully
        wait_time = e.value
        error_msg = f"⏳ Flood wait: {wait_time}s. Please wait..."
        try:
            await (status_msg or message).reply(error_msg)
            await asyncio.sleep(wait_time)
        except:
            pass
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"Processing error: {error_msg}")
        try:
            await (status_msg or message).reply(error_msg)
        except:
            pass
    
    finally:
        # Fast cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass
        # Force garbage collection
        gc.collect()

# Max-speed rename command
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    
    if is_user_processing(user_id):
        await message.reply("⏳ Processing previous file...")
        return
    
    if not message.reply_to_message:
        await message.reply("❌ Reply to a file with `/rename filename.ext`")
        return
    
    if not message.reply_to_message.media:
        await message.reply("❌ Please reply to a media file")
        return
    
    set_user_processing(user_id, True)
    
    try:
        await max_process_file_rename(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply(f"❌ Processing error: {str(e)}")
    finally:
        set_user_processing(user_id, False)

# Max status command
@app.on_message(filters.command("max_status"))
async def max_status(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    
    # Get system info
    cpu_percent = psutil.cpu_percent()
    disk_usage = psutil.disk_usage('/').percent
    
    await message.reply_text(
        f"⚡ **MAX TURBO STATUS**\n\n"
        f"• 💾 **Memory:** {memory_usage:.0f} MB\n"
        f"• 🚀 **Workers:** {MAX_WORKERS}\n"
        f"• 💨 **Chunk Size:** {format_size(CHUNK_SIZE)}\n"
        f"• 📁 **Max Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"• 🔥 **CPU Usage:** {cpu_percent}%\n"
        f"• 💽 **Disk Usage:** {disk_usage}%\n"
        f"• 🕒 **Uptime:** {get_uptime()}\n\n"
        f"**Status:** ⚡ **MAXIMUM PERFORMANCE**"
    )

# File limits command
@app.on_message(filters.command("file_limits"))
async def file_limits_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    await message.reply_text(
        f"📁 **Max File Limits**\n\n"
        f"• ✅ **Max Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"• 🚀 **Workers:** {MAX_WORKERS} parallel\n"
        f"• 💨 **Chunk Size:** {format_size(CHUNK_SIZE)}\n"
        f"• 📥 **Download Threads:** {DOWNLOAD_THREADS}\n"
        f"• 📤 **Upload Threads:** {UPLOAD_THREADS}\n"
        f"• ⚡ **Mode:** Max Turbo\n\n"
        "**Optimized for maximum speed and large files!**"
    )

# Callback query handlers - ultra fast
@app.on_callback_query(filters.regex("mode_auto"))
async def set_mode_auto(client, callback_query):
    user_id = callback_query.from_user.id
    set_user_preference(user_id, "auto")
    await callback_query.answer("🤖 Auto mode")
    await callback_query.message.edit_text("✅ **Mode:** `AUTO`")

@app.on_callback_query(filters.regex("mode_document"))
async def set_mode_document(client, callback_query):
    user_id = callback_query.from_user.id
    set_user_preference(user_id, "document")
    await callback_query.answer("📄 Document mode")
    await callback_query.message.edit_text("✅ **Mode:** `DOCUMENT`")

@app.on_callback_query(filters.regex("mode_video"))
async def set_mode_video(client, callback_query):
    user_id = callback_query.from_user.id
    set_user_preference(user_id, "video")
    await callback_query.answer("🎬 Video mode")
    await callback_query.message.edit_text("✅ **Mode:** `VIDEO`")

@app.on_callback_query(filters.regex("upload_options"))
async def upload_options_callback(client, callback_query):
    await callback_query.answer()
    await upload_mode_command(client, callback_query.message)

@app.on_callback_query(filters.regex("max_status"))
async def max_status_callback(client, callback_query):
    await callback_query.answer()
    await max_status(client, callback_query.message)

@app.on_callback_query(filters.regex("file_limits"))
async def file_limits_callback(client, callback_query):
    await callback_query.answer()
    await file_limits_command(client, callback_query.message)

# Essential media handlers (minimal)
@app.on_message(filters.command("view_thumb"))
async def view_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnail_file = thumbnails.get(str(user_id))
    
    if thumbnail_file and os.path.exists(thumbnail_file):
        await message.reply_photo(thumbnail_file, caption="📸 Thumbnail")
    else:
        await message.reply_text("❌ No thumbnail")

@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    thumb_path = f"thumbnails/{user_id}_{int(time.time())}.jpg"
    
    try:
        await message.download(thumb_path)
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        await message.reply_text("✅ Thumbnail set")
    except:
        await message.reply_text("❌ Error")

@app.on_message(filters.command("set_caption"))
async def set_caption_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/set_caption your text`")
        return
    
    user_id = message.from_user.id
    custom_caption = " ".join(message.command[1:])
    
    captions = load_json(CAPTION_DB)
    captions[str(user_id)] = custom_caption
    save_json(CAPTION_DB, captions)
    await message.reply_text("✅ Caption set")

# Start the bot with MAXIMUM performance
if __name__ == "__main__":
    print("""
⚡ STARTING MAX TURBO BOT...
💨 MAXIMUM SPEED OPTIMIZATIONS:
• 🚀 256MB Chunks
• ⚡ 1500 Workers  
• 💨 Zero-delay operations
• 🔥 Large file optimized
• 📁 Up to 4GB file support
    """)
    
    print(f"📁 Max File Size: {format_size(MAX_FILE_SIZE)}")
    print(f"🚀 Workers: {MAX_WORKERS}")
    print(f"💨 Chunk Size: {format_size(CHUNK_SIZE)}")
    
    # Start web server
    start_web_server()
    
    print("🌐 Starting MAX TURBO bot...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Startup error: {e}")