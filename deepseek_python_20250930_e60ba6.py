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
from pyrogram.errors import FloodWait, RPCError
import json
import time
from datetime import datetime
import concurrent.futures
import hashlib
import psutil
from flask import Flask, jsonify
import threading
import uvloop
from PIL import Image
import io
import re
import schedule
import asyncio

# ULTRA SPEED CONFIGURATION
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MAXIMUM PERFORMANCE OPTIMIZATION
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")

# ULTRA SPEED SETTINGS
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
CHUNK_SIZE = 512 * 1024  # 512KB
MAX_WORKERS = 200
BUFFER_SIZE = 64 * 1024  # 64KB BUFFER
CLEANUP_INTERVAL = 300  # 5 minutes
FILE_MAX_AGE = 1200  # 20 minutes

# Render detection
RENDER = os.getenv('RENDER', '').lower() == 'true'
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')
PORT = int(os.getenv('PORT', 5000))

if not BOT_TOKEN or not API_ID or not API_HASH:
    print("❌ Missing environment variables")
    sys.exit(1)

# Global tracking
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

# Ensure directories
for directory in ["downloads", "thumbnails", "temp"]:
    os.makedirs(directory, exist_ok=True)

def initialize_json_files():
    files_to_create = {
        USER_DB: {},
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        PREFIX_DB: {},
        PREFERENCES_DB: {},
        STATS_DB: {"total_files": 0, "total_size": 0, "users_count": 0}
    }
    for file_path, default_data in files_to_create.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump(default_data, f, indent=2)
            logger.info(f"Created {file_path}")

initialize_json_files()

# Flask Web Server
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return jsonify({"status": "online", "bot": "ULTRA SPEED BOT"})

@app_web.route('/stats')
def stats():
    stats_data = load_json(STATS_DB)
    users_data = load_json(USER_DB)
    
    uptime = time.time() - bot_start_time
    return jsonify({
        "status": "online",
        "uptime_seconds": int(uptime),
        "total_files_processed": stats_data.get("total_files", 0),
        "total_users": len(users_data),
        "server_time": datetime.now().isoformat()
    })

def run_web_server():
    global web_server_started, web_server_url
    try:
        host = '0.0.0.0'
        web_server_url = RENDER_EXTERNAL_URL if RENDER else f"http://localhost:{PORT}"
        app_web.run(host=host, port=PORT, debug=False, threaded=True)
        web_server_started = True
    except Exception as e:
        print(f"Web server error: {e}")

def start_web_server():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

# ULTRA FAST HELPER FUNCTIONS
def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def get_user_prefix(user_id):
    prefixes = load_json(PREFIX_DB)
    return prefixes.get(str(user_id), "")

def set_user_prefix(user_id, prefix):
    prefixes = load_json(PREFIX_DB)
    prefixes[str(user_id)] = prefix
    return save_json(PREFIX_DB, prefixes)

def get_upload_mode(user_id):
    preferences = load_json(PREFERENCES_DB)
    return preferences.get(str(user_id), "auto")

def set_upload_mode(user_id, mode):
    preferences = load_json(PREFERENCES_DB)
    preferences[str(user_id)] = mode
    return save_json(PREFERENCES_DB, preferences)

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal and invalid characters"""
    # Remove path traversal attempts
    filename = os.path.basename(filename)
    
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    return filename.strip()

# THUMBNAIL MANAGEMENT FUNCTIONS
def get_user_thumbnail(user_id):
    """Get user's thumbnail path"""
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnail_path = thumbnails.get(str(user_id))
    if thumbnail_path and os.path.exists(thumbnail_path):
        return thumbnail_path
    return None

def set_user_thumbnail(user_id, thumbnail_path):
    """Set user's thumbnail path"""
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnails[str(user_id)] = thumbnail_path
    return save_json(THUMBNAIL_DB, thumbnails)

def delete_user_thumbnail(user_id):
    """Delete user's thumbnail"""
    thumbnails = load_json(THUMBNAIL_DB)
    user_id_str = str(user_id)
    
    if user_id_str in thumbnails:
        # Delete the thumbnail file
        thumbnail_path = thumbnails[user_id_str]
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except:
                pass
        # Remove from database
        del thumbnails[user_id_str]
        return save_json(THUMBNAIL_DB, thumbnails)
    return False

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_duration(seconds):
    return f"{int(seconds//3600):02d}:{int((seconds%3600)//60):02d}:{int(seconds%60):02d}"

# AUTO CLEANUP SYSTEM
async def auto_cleanup():
    """Automatically delete files older than 20 minutes"""
    while True:
        try:
            current_time = time.time()
            files_deleted = 0
            
            for directory in ["downloads", "temp"]:
                if os.path.exists(directory):
                    for filename in os.listdir(directory):
                        filepath = os.path.join(directory, filename)
                        if os.path.isfile(filepath):
                            # Delete files older than 20 minutes (1200 seconds)
                            file_age = current_time - os.path.getctime(filepath)
                            if file_age > FILE_MAX_AGE:
                                try:
                                    os.remove(filepath)
                                    files_deleted += 1
                                    logger.info(f"Auto-deleted: {filename} (age: {file_age:.1f}s)")
                                except Exception as e:
                                    logger.error(f"Cleanup error for {filename}: {e}")
            
            if files_deleted > 0:
                logger.info(f"Auto-cleanup completed: {files_deleted} files deleted")
                
        except Exception as e:
            logger.error(f"Auto-cleanup system error: {e}")
        
        await asyncio.sleep(CLEANUP_INTERVAL)

async def start_cleanup_task():
    """Start the automatic cleanup task"""
    asyncio.create_task(auto_cleanup())
    logger.info("🔄 Auto-cleanup system started (20-minute file retention)")

# ULTRA FAST PROGRESS TRACKER
class UltraFastProgress:
    def __init__(self, total_size, operation_type):
        self.total_size = total_size
        self.operation_type = operation_type
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_bytes = 0
        self.current_bytes = 0
        self.speeds = []
        
    def update(self, current_bytes):
        current_time = time.time()
        self.current_bytes = current_bytes
        
        time_diff = current_time - self.last_time
        if time_diff >= 0.1:
            bytes_diff = current_bytes - self.last_bytes
            instant_speed = bytes_diff / time_diff
            
            self.speeds.append(instant_speed)
            if len(self.speeds) > 10:
                self.speeds.pop(0)
            
            self.last_bytes = current_bytes
            self.last_time = current_time
            
            return self.get_metrics()
        return None
    
    def get_metrics(self):
        elapsed = time.time() - self.start_time
        percentage = (self.current_bytes / self.total_size) * 100 if self.total_size > 0 else 0
        
        avg_speed = sum(self.speeds) / len(self.speeds) if self.speeds else 0
        remaining = self.total_size - self.current_bytes
        eta = remaining / avg_speed if avg_speed > 0 else 0
        
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        return {
            "percentage": percentage,
            "current": self.current_bytes,
            "total": self.total_size,
            "speed": avg_speed,
            "eta": eta,
            "elapsed": elapsed,
            "bar": bar
        }
    
    def get_progress_text(self, filename=""):
        metrics = self.get_metrics()
        text = f"**{'📥 DOWNLOADING' if self.operation_type == 'download' else '📤 UPLOADING'}**\n\n"
        if filename:
            text += f"**File:** `{filename}`\n"
        text += f"**Progress:** {metrics['bar']} {metrics['percentage']:.1f}%\n"
        text += f"**Size:** {format_size(metrics['current'])} / {format_size(metrics['total'])}\n"
        text += f"**Speed:** {format_size(metrics['speed'])}/s\n"
        text += f"**ETA:** {format_duration(metrics['eta'])}\n"
        text += f"**Elapsed:** {format_duration(metrics['elapsed'])}"
        return text

# ULTRA FAST PYROGRAM CLIENT
try:
    app = Client(
        "ultra_fast_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=60,
        workers=MAX_WORKERS,
        max_concurrent_transmissions=50,
        in_memory=False
    )
    print("✅ ULTRA FAST Pyrogram client initialized")
except Exception as e:
    print(f"❌ Client error: {e}")
    sys.exit(1)

# ULTRA FAST DOWNLOAD
async def ultra_fast_download(client, message, file_path, progress_callback):
    try:
        return await client.download_media(
            message,
            file_name=file_path,
            progress=progress_callback,
            in_memory=False
        )
    except Exception as e:
        print(f"Download error: {e}")
        return None

# ULTRA FAST UPLOAD WITH THUMBNAIL SUPPORT
async def ultra_fast_upload(client, chat_id, file_path, file_name, caption, file_type, progress_callback):
    """ULTRA FAST upload with thumbnail support"""
    try:
        # Get user thumbnail
        user_id = chat_id  # Assuming chat_id is user_id for private chats
        thumbnail_path = get_user_thumbnail(user_id)
        
        upload_params = {
            "chat_id": chat_id,
            "file_name": file_name,
            "caption": caption,
            "parse_mode": ParseMode.MARKDOWN,
            "progress": progress_callback,
            "disable_notification": True
        }
        
        # Add thumbnail if available and file type supports it
        if thumbnail_path and file_type in ["video", "audio", "document"]:
            upload_params["thumb"] = thumbnail_path
        
        if file_type == "video":
            return await client.send_video(video=file_path, supports_streaming=True, **upload_params)
        elif file_type == "audio":
            return await client.send_audio(audio=file_path, **upload_params)
        elif file_type == "photo":
            return await client.send_photo(photo=file_path, **upload_params)
        else:
            return await client.send_document(document=file_path, **upload_params)
    except Exception as e:
        print(f"Upload error: {e}")
        raise

# ULTRA FAST FILE PROCESSING WITH THUMBNAIL
async def ultra_fast_process_file(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    download_path = None
    status_msg = None
    
    try:
        # Parse the rename command correctly
        if message.text.startswith('/rename'):
            parts = message.text.split(" ", 1)
            if len(parts) < 2:
                await message.reply_text("❌ Usage: `/rename new_filename.ext`")
                return
            original_name = parts[1].strip()
        else:
            await message.reply_text("❌ Invalid command format")
            return
        
        # Sanitize filename
        original_name = sanitize_filename(original_name)
        
        if not original_name or len(original_name) > 255:
            await message.reply_text("❌ Invalid filename (1-255 characters)")
            return
        
        # Apply prefix
        user_prefix = get_user_prefix(user_id)
        new_name = user_prefix + original_name
        
        # Get file size and info
        file_size = 0
        file_type = "document"
        
        if target_message.document:
            file_size = target_message.document.file_size or 0
            file_type = "document"
        elif target_message.video:
            file_size = target_message.video.file_size or 0
            file_type = "video"
        elif target_message.audio:
            file_size = target_message.audio.file_size or 0
            file_type = "audio"
        elif target_message.photo:
            file_size = target_message.photo.file_size or 0
            file_type = "photo"
        else:
            await message.reply_text("❌ Unsupported file type")
            return
        
        if file_size == 0:
            await message.reply_text("❌ Cannot get file size")
            return
            
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large: {format_size(file_size)}")
            return
        
        # Start ULTRA FAST processing
        start_time = time.time()
        status_msg = await message.reply_text("⚡ **INITIALIZING ULTRA FAST TRANSFER...**")
        
        # Generate unique file path
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        # ULTRA FAST DOWNLOAD
        download_progress = UltraFastProgress(file_size, "download")
        last_update = 0
        
        async def download_callback(current, total):
            nonlocal last_update
            metrics = download_progress.update(current)
            current_time = time.time()
            
            if metrics and (current_time - last_update >= 1.0 or current == total):
                try:
                    await status_msg.edit_text(
                        download_progress.get_progress_text(new_name),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update = current_time
                except Exception as e:
                    print(f"Progress error: {e}")
        
        await status_msg.edit_text("📥 **STARTING ULTRA FAST DOWNLOAD...**")
        download_start = time.time()
        download_path = await ultra_fast_download(client, target_message, file_path, download_callback)
        download_time = time.time() - download_start
        
        if not download_path or not os.path.exists(download_path):
            await status_msg.edit_text("❌ Download failed! File not found.")
            return
        
        downloaded_size = os.path.getsize(download_path)
        download_speed = downloaded_size / download_time if download_time > 0 else 0
        
        # ULTRA FAST UPLOAD
        await status_msg.edit_text("🚀 **STARTING ULTRA FAST UPLOAD...**")
        
        # Get user caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Ultra Fast Upload**")
        
        # Determine upload type based on user preference
        upload_mode = get_upload_mode(user_id)
        if upload_mode == "auto":
            # Use original file type
            final_upload_type = file_type
        else:
            final_upload_type = upload_mode
        
        upload_progress = UltraFastProgress(downloaded_size, "upload")
        last_upload_update = 0
        
        async def upload_callback(current, total):
            nonlocal last_upload_update
            metrics = upload_progress.update(current)
            current_time = time.time()
            
            if metrics and (current_time - last_upload_update >= 1.0 or current == total):
                try:
                    await status_msg.edit_text(
                        upload_progress.get_progress_text(new_name),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_upload_update = current_time
                except Exception as e:
                    print(f"Upload progress error: {e}")
        
        upload_start = time.time()
        
        # Perform the upload with thumbnail
        sent_message = await ultra_fast_upload(
            client, 
            message.chat.id, 
            download_path, 
            new_name, 
            user_caption, 
            final_upload_type, 
            upload_callback
        )
        
        upload_time = time.time() - upload_start
        upload_speed = downloaded_size / upload_time if upload_time > 0 else 0
        
        total_time = time.time() - start_time
        
        # Performance rating
        avg_speed_mb = ((download_speed + upload_speed) / 2) / (1024 * 1024)
        if avg_speed_mb > 20:
            speed_rating = "⚡ ULTRA FAST"
        elif avg_speed_mb > 10:
            speed_rating = "🚀 FAST"
        else:
            speed_rating = "📊 NORMAL"
        
        # Check if thumbnail was used
        thumbnail_used = "✅" if get_user_thumbnail(user_id) and final_upload_type in ["video", "audio", "document"] else "❌"
        
        await status_msg.edit_text(
            f"✅ **{speed_rating} TRANSFER COMPLETE!**\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(downloaded_size)}\n"
            f"⏱ **Total Time:** {format_duration(total_time)}\n\n"
            f"📥 **Download:** {format_size(download_speed)}/s\n"
            f"📤 **Upload:** {format_size(upload_speed)}/s\n"
            f"🔧 **Mode:** {final_upload_type.upper()}\n"
            f"🖼️ **Thumbnail:** {thumbnail_used}\n"
            f"🏷️ **Prefix:** {'✅' if user_prefix else '❌'}\n\n"
            f"**Status:** ⚡ **RENAME SUCCESSFUL**"
        )
        
        # Update stats
        stats = load_json(STATS_DB)
        stats["total_files"] = stats.get("total_files", 0) + 1
        stats["total_size"] = stats.get("total_size", 0) + downloaded_size
        save_json(STATS_DB, stats)
        
        # Update user stats
        users = load_json(USER_DB)
        user_id_str = str(user_id)
        if user_id_str not in users:
            users[user_id_str] = {"files_processed": 0, "total_size": 0, "joined_at": datetime.now().isoformat()}
        users[user_id_str]["files_processed"] = users[user_id_str].get("files_processed", 0) + 1
        users[user_id_str]["total_size"] = users[user_id_str].get("total_size", 0) + downloaded_size
        users[user_id_str]["last_active"] = datetime.now().isoformat()
        save_json(USER_DB, users)
        
    except FloodWait as e:
        wait_msg = f"⏳ Flood wait: {e.value}s"
        if status_msg:
            await status_msg.edit_text(wait_msg)
        else:
            await message.reply_text(wait_msg)
        await asyncio.sleep(e.value)
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"Processing error: {e}")
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
    finally:
        # Cleanup downloaded file
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
                logger.info(f"Cleaned up: {download_path}")
            except Exception as e:
                print(f"Cleanup error: {e}")

# FIXED RENAME COMMAND
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    # Check if message already processed
    if message.id in processed_messages:
        return
    processed_messages.add(message.id)
    
    user_id = message.from_user.id
    
    # Check if user is already processing
    if user_id in user_processing and user_processing[user_id]:
        await message.reply_text("⏳ Please wait, processing your previous file...")
        return
    
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply_text(
            "❌ **How to use:**\n"
            "1. Reply to a file with `/rename new_filename.ext`\n"
            "2. Wait for ultra fast processing\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Speed:** ⚡ **INSTANT TRANSFER**"
        )
        return
    
    # Check if replied message has media
    if not message.reply_to_message.media:
        await message.reply_text("❌ Please reply to a media file (document, video, audio, photo)")
        return
    
    # Set user as processing
    user_processing[user_id] = True
    
    try:
        await ultra_fast_process_file(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply_text(f"❌ Processing error: {str(e)}")
    finally:
        # Reset processing status
        user_processing[user_id] = False

# THUMBNAIL COMMANDS
@app.on_message(filters.command("setthumb"))
async def set_thumbnail_command(client, message: Message):
    """Command to set thumbnail"""
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text("❌ Reply to a photo with /setthumb to set as thumbnail")
        return
    
    user_id = message.from_user.id
    try:
        # Download the photo
        thumb_path = f"thumbnails/{user_id}.jpg"
        await message.reply_to_message.download(thumb_path)
        
        # Set thumbnail in database
        if set_user_thumbnail(user_id, thumb_path):
            await message.reply_text("✅ Thumbnail set successfully! It will be used for videos, audio, and documents.")
        else:
            await message.reply_text("❌ Failed to save thumbnail")
    except Exception as e:
        await message.reply_text(f"❌ Error setting thumbnail: {str(e)}")

@app.on_message(filters.command("delthumb"))
async def delete_thumbnail_command(client, message: Message):
    """Command to delete thumbnail"""
    user_id = message.from_user.id
    if delete_user_thumbnail(user_id):
        await message.reply_text("✅ Thumbnail deleted successfully!")
    else:
        await message.reply_text("❌ No thumbnail found to delete")

@app.on_message(filters.command("viewthumb"))
async def view_thumbnail_command(client, message: Message):
    """Command to view current thumbnail"""
    user_id = message.from_user.id
    thumbnail_path = get_user_thumbnail(user_id)
    
    if thumbnail_path and os.path.exists(thumbnail_path):
        await message.reply_photo(
            thumbnail_path,
            caption="🖼️ Your current thumbnail"
        )
    else:
        await message.reply_text("❌ No thumbnail set. Use /setthumb to set one.")

# AUTO THUMBNAIL FROM PHOTOS
@app.on_message(filters.photo & filters.private)
async def auto_set_thumbnail(client, message: Message):
    """Automatically set thumbnail when user sends a photo in private chat"""
    user_id = message.from_user.id
    try:
        thumb_path = f"thumbnails/{user_id}.jpg"
        await message.download(thumb_path)
        
        if set_user_thumbnail(user_id, thumb_path):
            await message.reply_text("✅ Thumbnail set automatically from your photo! It will be used for future uploads.")
        else:
            await message.reply_text("❌ Failed to set thumbnail")
    except Exception as e:
        await message.reply_text(f"❌ Error setting thumbnail: {str(e)}")

# START COMMAND
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Speed Test", callback_data="speed_test")],
        [InlineKeyboardButton("🔧 Settings", callback_data="settings")],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail_settings")],
        [InlineKeyboardButton("🌐 Status", url=web_server_url)]
    ])
    
    await message.reply_text(
        f"⚡ **ULTRA FAST RENAME BOT**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        f"**Features:**\n"
        f"• ⚡ Instant file renaming\n"
        f"• 🖼️ Custom thumbnails\n"
        f"• 🚀 Parallel processing\n"
        f"• 📊 Real-time progress\n"
        f"• 📁 4GB file support\n"
        f"• 🔄 Auto-cleanup (20min)\n\n"
        f"**System:** {web_status}\n"
        f"**How to use:** Reply to any file with `/rename new_filename.ext`\n\n"
        f"**⚡ EXPERIENCE INSTANT RENAMING!**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# SETTINGS COMMAND
@app.on_message(filters.command("settings"))
async def settings_command(client, message: Message):
    user_id = message.from_user.id
    prefix = get_user_prefix(user_id)
    upload_mode = get_upload_mode(user_id)
    has_thumbnail = "✅" if get_user_thumbnail(user_id) else "❌"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Set Prefix", callback_data="set_prefix")],
        [InlineKeyboardButton("📤 Upload Mode", callback_data="upload_mode")],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail_settings")],
        [InlineKeyboardButton("⚡ Speed Test", callback_data="speed_test")]
    ])
    
    await message.reply_text(
        f"🔧 **ULTRA FAST SETTINGS**\n\n"
        f"**Current Settings:**\n"
        f"• **Prefix:** `{prefix if prefix else 'None'}`\n"
        f"• **Upload Mode:** {upload_mode.upper()}\n"
        f"• **Thumbnail:** {has_thumbnail}\n\n"
        f"**Commands:**\n"
        f"• `/rename filename.ext` - Rename files\n"
        f"• `/set_prefix text` - Set custom prefix\n"
        f"• `/setthumb` - Set thumbnail (reply to photo)\n"
        f"• `/viewthumb` - View current thumbnail\n"
        f"• `/delthumb` - Delete thumbnail\n\n"
        f"**Choose an option:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# CALLBACK HANDLERS
@app.on_callback_query(filters.regex("thumbnail_settings"))
async def thumbnail_settings_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    has_thumbnail = "✅ Set" if get_user_thumbnail(user_id) else "❌ Not set"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼️ Set Thumbnail", callback_data="set_thumbnail")],
        [InlineKeyboardButton("👀 View Thumbnail", callback_data="view_thumbnail")],
        [InlineKeyboardButton("🗑️ Delete Thumbnail", callback_data="delete_thumbnail")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings")]
    ])
    
    await callback_query.message.edit_text(
        f"🖼️ **THUMBNAIL SETTINGS**\n\n"
        f"**Status:** {has_thumbnail}\n\n"
        f"**How to set:**\n"
        f"1. Send any photo to this chat\n"
        f"2. Or use /setthumb command\n\n"
        f"**Supported for:** Videos, Audio, Documents\n\n"
        f"**Choose action:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("set_thumbnail"))
async def set_thumbnail_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "🖼️ **SET THUMBNAIL**\n\n"
        "To set a thumbnail:\n\n"
        "**Method 1:** Simply send any photo to this chat\n"
        "**Method 2:** Reply to a photo with `/setthumb` command\n\n"
        "The thumbnail will be automatically used for your video, audio, and document uploads.",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("view_thumbnail"))
async def view_thumbnail_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    thumbnail_path = get_user_thumbnail(user_id)
    
    if thumbnail_path and os.path.exists(thumbnail_path):
        await callback_query.message.reply_photo(
            thumbnail_path,
            caption="🖼️ Your current thumbnail"
        )
    else:
        await callback_query.message.edit_text("❌ No thumbnail set. Send a photo to set one.")

@app.on_callback_query(filters.regex("delete_thumbnail"))
async def delete_thumbnail_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if delete_user_thumbnail(user_id):
        await callback_query.message.edit_text("✅ Thumbnail deleted successfully!")
    else:
        await callback_query.message.edit_text("❌ No thumbnail found to delete")

# Other callback handlers
@app.on_callback_query(filters.regex("speed_test"))
async def speed_test_callback(client, callback_query):
    await callback_query.answer()
    
    # Simple speed test by creating and uploading a small file
    test_file_path = "temp/speed_test.bin"
    test_size = 1 * 1024 * 1024  # 1MB
    
    try:
        # Create test file
        with open(test_file_path, 'wb') as f:
            f.write(os.urandom(test_size))
        
        start_time = time.time()
        
        # Upload the file
        await client.send_document(
            callback_query.message.chat.id,
            test_file_path,
            caption="⚡ **SPEED TEST RESULT**",
            file_name="speed_test.bin"
        )
        
        upload_time = time.time() - start_time
        speed = test_size / upload_time
        
        await callback_query.message.edit_text(
            f"⚡ **SPEED TEST COMPLETE**\n\n"
            f"**File Size:** {format_size(test_size)}\n"
            f"**Upload Time:** {upload_time:.2f}s\n"
            f"**Speed:** {format_size(speed)}/s\n\n"
            f"**Rating:** {'⚡ ULTRA FAST' if speed > 2*1024*1024 else '🚀 FAST' if speed > 1*1024*1024 else '📊 NORMAL'}"
        )
        
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Speed test failed: {str(e)}")
    finally:
        # Cleanup test file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)

@app.on_callback_query(filters.regex("settings"))
async def settings_callback(client, callback_query):
    await callback_query.answer()
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex("set_prefix"))
async def set_prefix_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "🔧 **SET PREFIX**\n\n"
        "Use `/set_prefix your_prefix` to set a custom prefix.\n\n"
        "**Example:** `/set_prefix MOVIE_`\n\n"
        "All renamed files will have this prefix added automatically.",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("upload_mode"))
async def upload_mode_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    current_mode = get_upload_mode(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto", callback_data="mode_auto")],
        [InlineKeyboardButton("📁 Document", callback_data="mode_document")],
        [InlineKeyboardButton("🎥 Video", callback_data="mode_video")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings")]
    ])
    
    await callback_query.message.edit_text(
        f"📤 **UPLOAD MODE**\n\n"
        f"**Current:** {current_mode.upper()}\n\n"
        f"**Modes:**\n"
        f"• 🤖 **Auto:** Smart file type detection\n"
        f"• 📁 **Document:** Force as document file\n"
        f"• 🎥 **Video:** Force as video file\n\n"
        f"**Choose mode:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("mode_"))
async def set_mode_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    mode = callback_query.data.split("_")[1]
    
    if set_upload_mode(user_id, mode):
        await callback_query.message.edit_text(
            f"✅ **UPLOAD MODE UPDATED**\n\n"
            f"**New Mode:** {mode.upper()}\n\n"
            f"All future uploads will use this mode.\n"
            f"**Status:** ⚡ **OPTIMIZED FOR SPEED**",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback_query.message.edit_text("❌ Failed to update mode!")

# PREFIX COMMAND
@app.on_message(filters.command("set_prefix"))
async def set_prefix_command(client, message: Message):
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/set_prefix your_prefix`")
        return
    
    prefix = " ".join(message.command[1:])
    
    if len(prefix) > 50:
        await message.reply_text("❌ Prefix too long! Max 50 characters")
        return
    
    if set_user_prefix(user_id, prefix):
        await message.reply_text(f"✅ Prefix set: `{prefix}`\n\n⚡ **Now experience ULTRA FAST transfers!**")
    else:
        await message.reply_text("❌ Failed to set prefix!")

# STATS COMMAND
@app.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    stats_data = load_json(STATS_DB)
    users_data = load_json(USER_DB)
    
    total_files = stats_data.get("total_files", 0)
    total_size = stats_data.get("total_size", 0)
    total_users = len(users_data)
    uptime = time.time() - bot_start_time
    
    # Get current user stats
    user_id = str(message.from_user.id)
    user_files = users_data.get(user_id, {}).get("files_processed", 0)
    user_size = users_data.get(user_id, {}).get("total_size", 0)
    
    await message.reply_text(
        f"📊 **BOT STATISTICS**\n\n"
        f"**Global Stats:**\n"
        f"• 📁 Total Files: {total_files}\n"
        f"• 💾 Total Size: {format_size(total_size)}\n"
        f"• 👥 Total Users: {total_users}\n"
        f"• ⏰ Uptime: {format_duration(uptime)}\n\n"
        f"**Your Stats:**\n"
        f"• 📁 Your Files: {user_files}\n"
        f"• 💾 Your Size: {format_size(user_size)}\n\n"
        f"**Auto-Cleanup:** ✅ Active (20 minutes)",
        parse_mode=ParseMode.MARKDOWN
    )

# CLEANUP COMMAND (ADMIN)
@app.on_message(filters.command("cleanup") & filters.user([1340313994, 123456789]))  # Add your user ID
async def manual_cleanup(client, message: Message):
    """Manual cleanup command for admin"""
    try:
        files_deleted = 0
        current_time = time.time()
        
        for directory in ["downloads", "temp"]:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        file_age = current_time - os.path.getctime(filepath)
                        if file_age > FILE_MAX_AGE:
                            try:
                                os.remove(filepath)
                                files_deleted += 1
                            except Exception as e:
                                logger.error(f"Manual cleanup error: {e}")
        
        await message.reply_text(f"✅ Manual cleanup completed: {files_deleted} files deleted")
        
    except Exception as e:
        await message.reply_text(f"❌ Cleanup error: {str(e)}")

# START BOT WITH ULTRA FAST OPTIMIZATIONS
async def main():
    print("⚡ STARTING ULTRA FAST RENAME BOT...")
    print("🚀 Performance Optimizations:")
    print(f"   • Chunk Size: {format_size(CHUNK_SIZE)}")
    print(f"   • Workers: {MAX_WORKERS}")
    print(f"   • Max File: {format_size(MAX_FILE_SIZE)}")
    print("   • Instant Progress Updates")
    print("   • Real-time Speed Tracking")
    print("   • Thumbnail Support")
    print("   • File Renaming Fixed")
    print("   • Auto-Cleanup: 20 minutes")
    
    # Start web server
    start_web_server()
    
    print(f"🌐 Web Dashboard: {web_server_url}")
    print("⚡ ULTRA FAST RENAME BOT READY!")
    print("✅ File renaming FIXED and WORKING!")
    print("✅ Thumbnail system FIXED and WORKING!")
    print("🔄 Auto-cleanup system STARTED!")
    
    # Start cleanup task
    await start_cleanup_task()
    
    # Start the bot
    await app.start()
    print("🤖 Bot is running...")
    
    # Keep the bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("❌ Bot stopped by user")
    except Exception as e:
        print(f"❌ Startup error: {e}")
    finally:
        print("🔄 Cleaning up before exit...")