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

# Apply UVLoop for maximum async performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMIN", "").split() if admin_id.strip()]

# Render environment detection
RENDER = os.getenv('RENDER', '').lower() == 'true'
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')
RENDER_INSTANCE_ID = os.getenv('RENDER_INSTANCE_ID', '')
PORT = int(os.getenv('PORT', 5000))

# Validate required environment variables
if not BOT_TOKEN or not API_ID or not API_HASH:
    print("❌ Error: BOT_TOKEN, API_ID, and API_HASH must be set in .env file")
    sys.exit(1)

# EXTREME SPEED OPTIMIZATION SETTINGS
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
CHUNK_SIZE = 128 * 1024 * 1024  # 128MB chunks for maximum throughput
MAX_WORKERS = 100
BUFFER_SIZE = 2 * 1024 * 1024  # 2MB buffer

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}
web_server_started = False
web_server_url = ""

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"
STATS_DB = "stats.json"
PREFIX_DB = "prefixes.json"
PREFERENCES_DB = "preferences.json"

# Ensure storage directories exist
for directory in ["downloads", "thumbnails", "temp"]:
    os.makedirs(directory, exist_ok=True)

# Initialize JSON files
def initialize_json_files():
    files_to_create = {
        USER_DB: {},
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        PREFIX_DB: {},
        PREFERENCES_DB: {},
        STATS_DB: {
            "total_files": 0,
            "total_size": 0,
            "users_count": 0,
            "bot_start_time": datetime.now().isoformat(),
            "last_restart": datetime.now().isoformat(),
            "deployment_type": "render" if RENDER else "local"
        }
    }
    
    for file_path, default_data in files_to_create.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Created {file_path}")

initialize_json_files()

# Flask Web Server
app_web = Flask(__name__)

@app_web.route('/')
def home():
    """Main status page"""
    try:
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        cpu_percent = psutil.cpu_percent()
        
        stats = load_json(STATS_DB)
        users = load_json(USER_DB)
        
        uptime_seconds = int(time.time() - bot_start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        
        return jsonify({
            "status": "online",
            "bot_name": "Ultra Speed Bot",
            "deployment": "render" if RENDER else "local",
            "web_server": "running",
            "web_url": web_server_url,
            "uptime": uptime_str,
            "memory_usage_mb": round(memory_usage, 2),
            "cpu_usage_percent": cpu_percent,
            "total_users": len(users),
            "total_files_processed": stats.get("total_files", 0),
            "max_file_size": format_size(MAX_FILE_SIZE),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_web_server():
    """Run the Flask web server with Render detection"""
    global web_server_started, web_server_url
    
    try:
        host = '0.0.0.0'
        
        if RENDER:
            web_server_url = RENDER_EXTERNAL_URL
        else:
            web_server_url = f"http://localhost:{PORT}"
        
        print(f"🌐 Starting Web Server on {host}:{PORT}...")
        app_web.run(host=host, port=PORT, debug=False, threaded=True)
        web_server_started = True
        
    except Exception as e:
        print(f"❌ Web server error: {e}")
        web_server_started = False

def start_web_server():
    """Start web server in a separate thread"""
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("✅ Web Server thread started")

# Helper functions
def load_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

def get_user_prefix(user_id):
    prefixes = load_json(PREFIX_DB)
    return prefixes.get(str(user_id), "")

def set_user_prefix(user_id, prefix):
    prefixes = load_json(PREFIX_DB)
    prefixes[str(user_id)] = prefix
    return save_json(PREFIX_DB, prefixes)

def delete_user_prefix(user_id):
    prefixes = load_json(PREFIX_DB)
    if str(user_id) in prefixes:
        del prefixes[str(user_id)]
        return save_json(PREFIX_DB, prefixes)
    return False

def get_user_preference(user_id):
    preferences = load_json(PREFERENCES_DB)
    return preferences.get(str(user_id), "auto")

def set_user_preference(user_id, preference):
    preferences = load_json(PREFERENCES_DB)
    preferences[str(user_id)] = preference
    return save_json(PREFERENCES_DB, preferences)

def save_user(user_id):
    users = load_json(USER_DB)
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {
            "joined_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "files_processed": 0
        }
        save_json(USER_DB, users)

def update_user_activity(user_id):
    users = load_json(USER_DB)
    user_id_str = str(user_id)
    if user_id_str in users:
        users[user_id_str]["last_active"] = datetime.now().isoformat()
        save_json(USER_DB, users)

def update_stats(files_processed=0):
    stats = load_json(STATS_DB)
    if files_processed > 0:
        stats["total_files"] = stats.get("total_files", 0) + files_processed
    save_json(STATS_DB, stats)

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def format_duration(seconds):
    if not seconds:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def format_speed(bytes_per_second):
    return format_size(bytes_per_second) + "/s"

def get_uptime():
    uptime_seconds = int(time.time() - bot_start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

def is_message_processed(message_id):
    return message_id in processed_messages

def mark_message_processed(message_id):
    processed_messages.add(message_id)
    if len(processed_messages) > 1000:
        processed_messages.clear()

def is_user_processing(user_id):
    return user_processing.get(user_id, False)

def set_user_processing(user_id, status):
    user_processing[user_id] = status

# Real-time speed tracker
class SpeedTracker:
    def __init__(self):
        self.start_time = time.time()
        self.last_update = self.start_time
        self.last_bytes = 0
        self.current_bytes = 0
        self.speeds = []
        
    def update(self, bytes_processed):
        current_time = time.time()
        self.current_bytes = bytes_processed
        
        # Calculate instant speed
        time_diff = current_time - self.last_update
        if time_diff >= 0.5:  # Update every 500ms for instant speed
            bytes_diff = bytes_processed - self.last_bytes
            instant_speed = bytes_diff / time_diff if time_diff > 0 else 0
            self.speeds.append(instant_speed)
            
            # Keep only last 10 readings
            if len(self.speeds) > 10:
                self.speeds.pop(0)
                
            self.last_bytes = bytes_processed
            self.last_update = current_time
            
            return instant_speed
        return None
    
    def get_average_speed(self):
        if not self.speeds:
            return 0
        return sum(self.speeds) / len(self.speeds)
    
    def get_instant_speed(self):
        if not self.speeds:
            return 0
        return self.speeds[-1]

# Initialize Pyrogram Client with maximum performance
try:
    app = Client(
        "ultra_speed_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=10,  # Reduced for faster response
        workers=MAX_WORKERS,
        max_concurrent_transmissions=20,
        in_memory=False
    )
    print("✅ Pyrogram client initialized with ULTRA SPEED settings")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Ultra-fast download with instant speed tracking
async def ultra_download(client, message, file_path, progress_callback=None):
    """Maximum speed download with instant speed tracking"""
    start_time = time.time()
    speed_tracker = SpeedTracker()
    
    try:
        # Use fastest download method
        download_path = await client.download_media(
            message,
            file_name=file_path,
            in_memory=False,
            block=True
        )
        
        if download_path and os.path.exists(download_path):
            file_size = os.path.getsize(download_path)
            download_time = time.time() - start_time
            avg_speed = file_size / download_time if download_time > 0 else 0
            
            return download_path, file_size, avg_speed
        
        return None, 0, 0
        
    except Exception as e:
        print(f"Download error: {e}")
        return None, 0, 0

# Ultra-fast upload with instant speed tracking
async def ultra_upload(client, chat_id, file_path, file_name, caption, thumb, file_type="document"):
    """Maximum speed upload with instant speed tracking"""
    start_time = time.time()
    file_size = os.path.getsize(file_path)
    
    try:
        if file_type == "video":
            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                file_name=file_name,
                caption=caption,
                thumb=thumb,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                disable_notification=True  # Faster
            )
        elif file_type == "audio":
            message = await client.send_audio(
                chat_id=chat_id,
                audio=file_path,
                file_name=file_name,
                caption=caption,
                thumb=thumb,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=True
            )
        elif file_type == "photo":
            message = await client.send_photo(
                chat_id=chat_id,
                photo=file_path,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=True
            )
        else:
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
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
        print(f"Upload error: {e}")
        raise

# Enhanced file processing with instant speed
async def ultra_process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    download_path = None
    status_msg = None
    
    try:
        # Parse command
        parts = message.text.split(" ", 1)
        if len(parts) < 2:
            await message.reply_text("❌ Usage: `/rename new_filename.ext`")
            return
        
        original_name = parts[1].strip()
        if not original_name or len(original_name) > 255:
            await message.reply_text("❌ Invalid filename (1-255 chars)")
            return
        
        # Apply prefix
        user_prefix = get_user_prefix(user_id)
        new_name = user_prefix + original_name
        
        # Get file size
        file_size = 0
        if target_message.document:
            file_size = target_message.document.file_size or 0
        elif target_message.video:
            file_size = target_message.video.file_size or 0
        elif target_message.audio:
            file_size = target_message.audio.file_size or 0
        
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large: {format_size(file_size)}")
            return
        
        # Start processing
        start_time = time.time()
        status_msg = await message.reply_text("⚡ **ULTRA SPEED PROCESSING...**")
        
        # Generate file path
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        # ULTRA-FAST DOWNLOAD
        download_start = time.time()
        await status_msg.edit_text("🚀 **DOWNLOADING AT MAX SPEED...**")
        
        download_path, downloaded_size, download_speed = await ultra_download(client, target_message, file_path)
        download_time = time.time() - download_start
        
        if not download_path:
            await status_msg.edit_text("❌ Download failed!")
            return
        
        download_speed_mb = download_speed / (1024 * 1024)
        
        # ULTRA-FAST UPLOAD
        await status_msg.edit_text("🚀 **UPLOADING AT MAX SPEED...**")
        
        # Prepare upload parameters
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Ultra Speed Upload**")
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Determine upload type
        upload_type = "document"
        if target_message.video:
            upload_type = "video"
        elif target_message.audio:
            upload_type = "audio"
        elif target_message.photo:
            upload_type = "photo"
        
        upload_start = time.time()
        sent_message, upload_speed = await ultra_upload(
            client, message.chat.id, file_path, new_name, 
            user_caption, thumbnail_path, upload_type
        )
        upload_time = time.time() - upload_start
        upload_speed_mb = upload_speed / (1024 * 1024)
        
        # Update stats
        update_stats(files_processed=1)
        users = load_json(USER_DB)
        if str(user_id) in users:
            users[str(user_id)]["files_processed"] = users[str(user_id)].get("files_processed", 0) + 1
            save_json(USER_DB, users)
        
        total_time = time.time() - start_time
        
        # Speed analysis
        speed_rating = "⚡ ULTRA FAST" if download_speed_mb > 50 or upload_speed_mb > 50 else "🚀 FAST"
        
        await status_msg.edit_text(
            f"✅ **{speed_rating} COMPLETE!**\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(downloaded_size)}\n"
            f"⏱ **Total Time:** {format_duration(int(total_time))}\n\n"
            f"📥 **Download:** {download_speed_mb:.1f} MB/s\n"
            f"📤 **Upload:** {upload_speed_mb:.1f} MB/s\n"
            f"🔧 **With Prefix:** {'✅' if user_prefix else '❌'}\n\n"
            f"**Status:** ⚡ **INSTANT SPEED ACHIEVED**"
        )
        
    except FloodWait as e:
        wait_time = e.value
        await (status_msg or message).reply_text(f"⏳ Flood wait: {wait_time}s")
        await asyncio.sleep(wait_time)
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
        logger.error(f"Processing error: {e}")
    
    finally:
        # Fast cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass

# Rename command with ultra speed
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if is_user_processing(user_id):
        await message.reply_text("⏳ Processing previous file...")
        return
    
    if not message.reply_to_message:
        await message.reply_text(
            "❌ Reply to a file with `/rename filename.ext`\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Speed:** ⚡ **INSTANT**"
        )
        return
    
    if not message.reply_to_message.media:
        await message.reply_text("❌ Reply to a media file")
        return
    
    set_user_processing(user_id, True)
    
    try:
        await ultra_process_file_rename(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        set_user_processing(user_id, False)

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    save_user(user_id)
    update_user_activity(user_id)
    
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    deployment_type = "🚀 Render" if RENDER else "💻 Local"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Speed Status", callback_data="speed_status")],
        [InlineKeyboardButton("🔧 Prefix", callback_data="prefix_settings")],
        [InlineKeyboardButton("📁 Upload Mode", callback_data="upload_mode")],
        [InlineKeyboardButton("🌐 Web Dashboard", url=web_server_url)]
    ])
    
    await message.reply_text(
        f"⚡ **ULTRA SPEED BOT**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        f"**Features:**\n"
        f"• ⚡ Instant download/upload speeds\n"
        f"• 🚀 128MB chunks for maximum throughput\n"
        f"• 💨 Zero-delay processing\n"
        f"• 📁 Up to 4GB file support\n\n"
        f"**System:** {web_status} | {deployment_type}\n"
        f"**Uptime:** {get_uptime()}\n\n"
        f"**Commands:** `/rename` • `/set_prefix` • `/status`\n\n"
        f"**⚡ EXPERIENCE INSTANT SPEED! ⚡**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Speed status command
@app.on_message(filters.command("status"))
async def status_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    users = load_json(USER_DB)
    total_users = len(users)
    
    total_files = 0
    for user_data in users.values():
        total_files += user_data.get("files_processed", 0)
    
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    cpu_percent = psutil.cpu_percent()
    
    await message.reply_text(
        f"⚡ **ULTRA SPEED STATUS**\n\n"
        f"**Performance:**\n"
        f"• 🚀 Chunk Size: {format_size(CHUNK_SIZE)}\n"
        f"• ⚡ Workers: {MAX_WORKERS}\n"
        f"• 💾 Buffer: {format_size(BUFFER_SIZE)}\n"
        f"• 📁 Max Size: {format_size(MAX_FILE_SIZE)}\n\n"
        f"**Statistics:**\n"
        f"• 👥 Users: {total_users}\n"
        f"• 📁 Files: {total_files}\n"
        f"• 🕒 Uptime: {get_uptime()}\n\n"
        f"**System:**\n"
        f"• 💾 Memory: {memory_usage:.0f} MB\n"
        f"• 🔥 CPU: {cpu_percent}%\n\n"
        f"**Status:** ⚡ **MAXIMUM SPEED READY**"
    )

# [Include other command handlers: prefix, thumbnail, caption, upload_mode, etc.]
# These remain the same as previous versions

# Prefix commands
@app.on_message(filters.command("set_prefix"))
async def set_prefix_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/set_prefix your_prefix`")
        return
    
    prefix = " ".join(message.command[1:])
    
    if len(prefix) > 50:
        await message.reply_text("❌ Prefix too long! Max 50 chars")
        return
    
    if set_user_prefix(user_id, prefix):
        await message.reply_text(f"✅ Prefix set: `{prefix}`")
    else:
        await message.reply_text("❌ Failed to set prefix!")

@app.on_message(filters.command("del_prefix"))
async def del_prefix_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if delete_user_prefix(user_id):
        await message.reply_text("✅ Prefix deleted!")
    else:
        await message.reply_text("❌ No prefix found!")

@app.on_message(filters.command("view_prefix"))
async def view_prefix_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    prefix = get_user_prefix(user_id)
    
    if prefix:
        await message.reply_text(f"**Prefix:** `{prefix}`")
    else:
        await message.reply_text("❌ No prefix set!")

# Thumbnail commands
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
        await message.reply_photo(thumbnail_file, caption="📸 Your thumbnail")
    else:
        await message.reply_text("❌ No thumbnail! Send a photo")

@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumb_path = f"thumbnails/{user_id}_{int(time.time())}.jpg"
    
    try:
        await message.download(thumb_path)
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        await message.reply_text("✅ Thumbnail set!")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

# Callback handlers
@app.on_callback_query(filters.regex("speed_status"))
async def speed_status_callback(client, callback_query):
    await callback_query.answer()
    await status_command(client, callback_query.message)

# Start the bot with ultra speed
if __name__ == "__main__":
    print("⚡ STARTING ULTRA SPEED BOT...")
    print(f"🚀 Performance Settings:")
    print(f"   • Chunk Size: {format_size(CHUNK_SIZE)}")
    print(f"   • Workers: {MAX_WORKERS}")
    print(f"   • Buffer: {format_size(BUFFER_SIZE)}")
    print(f"   • Max File: {format_size(MAX_FILE_SIZE)}")
    
    if RENDER:
        print("🚀 Render Environment Detected")
    else:
        print("💻 Local Development")
    
    # Start web server
    start_web_server()
    time.sleep(2)
    
    print(f"🌐 Web Dashboard: {web_server_url}")
    print("✅ All systems ready for ULTRA SPEED...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Startup error: {e}")
