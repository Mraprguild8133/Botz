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
MAX_WORKERS = min(200, multiprocessing.cpu_count() * 20)
CHUNK_SIZE = 256 * 1024 * 1024
DOWNLOAD_THREADS = 64
UPLOAD_THREADS = 48
BUFFER_SIZE = 4 * 1024 * 1024
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024
PARALLEL_DOWNLOADS = 32
PARALLEL_UPLOADS = 24

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}
user_upload_preferences = {}
active_downloads = {}
active_uploads = {}
user_prefixes = {}

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"
STATS_DB = "stats.json"
SPEED_DB = "speed_stats.json"
PREFERENCES_DB = "preferences.json"
PREFIX_DB = "prefixes.json"

# Ensure storage directories exist
for directory in ["downloads", "thumbnails", "temp", "templates", "large_files", "cache"]:
    os.makedirs(directory, exist_ok=True)

# Initialize JSON files
def initialize_json_files():
    files_to_create = {
        USER_DB: {},
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        PREFERENCES_DB: {},
        PREFIX_DB: {},
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

initialize_json_files()

# Helper functions
def load_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        return True
    except:
        return False

def get_user_prefix(user_id):
    prefixes = load_json(PREFIX_DB)
    return prefixes.get(str(user_id), "")

def set_user_prefix(user_id, prefix):
    prefixes = load_json(PREFIX_DB)
    prefixes[str(user_id)] = prefix
    save_json(PREFIX_DB, prefixes)
    user_prefixes[str(user_id)] = prefix
    return True

def delete_user_prefix(user_id):
    prefixes = load_json(PREFIX_DB)
    if str(user_id) in prefixes:
        del prefixes[str(user_id)]
        save_json(PREFIX_DB, prefixes)
        if str(user_id) in user_prefixes:
            del user_prefixes[str(user_id)]
        return True
    return False

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def format_duration(seconds):
    if not seconds:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def format_speed(bytes_per_second):
    return format_size(bytes_per_second) + "/s"

def calculate_eta(current, total, speed):
    if speed <= 0:
        return "Calculating..."
    remaining = total - current
    eta_seconds = remaining / speed
    return format_duration(int(eta_seconds))

def create_progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    empty = length - filled
    return "█" * filled + "░" * empty

# Real-time progress tracking class
class ProgressTracker:
    def __init__(self, user_id, operation_type, total_size):
        self.user_id = user_id
        self.operation_type = operation_type  # "download" or "upload"
        self.total_size = total_size
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_bytes = 0
        self.current_bytes = 0
        self.speed = 0
        self.eta = "Calculating..."
        
    def update(self, current_bytes):
        current_time = time.time()
        self.current_bytes = current_bytes
        
        # Calculate speed (bytes per second)
        time_diff = current_time - self.last_update_time
        if time_diff >= 1.0:  # Update speed every second
            bytes_diff = current_bytes - self.last_bytes
            self.speed = bytes_diff / time_diff if time_diff > 0 else 0
            self.last_bytes = current_bytes
            self.last_update_time = current_time
            
            # Calculate ETA
            if self.speed > 0:
                self.eta = calculate_eta(current_bytes, self.total_size, self.speed)
        
    def get_progress_text(self, filename=""):
        percentage = (self.current_bytes / self.total_size) * 100 if self.total_size > 0 else 0
        progress_bar = create_progress_bar(percentage)
        
        text = f"**{'📥 DOWNLOADING' if self.operation_type == 'download' else '📤 UPLOADING'}**\n\n"
        
        if filename:
            text += f"**File:** `{filename}`\n"
        
        text += f"**Progress:** {progress_bar} {percentage:.1f}%\n"
        text += f"**Size:** {format_size(self.current_bytes)} / {format_size(self.total_size)}\n"
        text += f"**Speed:** {format_speed(self.speed)}\n"
        text += f"**ETA:** {self.eta}\n"
        text += f"**Elapsed:** {format_duration(time.time() - self.start_time)}"
        
        return text

# Flask Web Server
app_web = Flask(__name__)

@app_web.route('/')
def home():
    try:
        return jsonify({
            "status": "online",
            "bot_name": "MAX TURBO BOT",
            "max_file_size": format_size(MAX_FILE_SIZE),
            "timestamp": datetime.now().isoformat()
        })
    except:
        return jsonify({"status": "error"}), 500

def run_web_server():
    print("🌐 Starting Web Server on port 5000...")
    app_web.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def start_web_server():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("✅ Web Server started on http://0.0.0.0:5000")

# Initialize Pyrogram Client
try:
    app = Client(
        "max_turbo_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=2,
        workers=1500,
        max_concurrent_transmissions=100,
        in_memory=False,
        ipv6=False
    )
    print("🚀 Pyrogram client initialized with MAXIMUM performance settings")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Prefix commands
@app.on_message(filters.command("set_prefix"))
async def set_prefix_command(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/set_prefix your_prefix`\n\n"
            "**Example:** `/set_prefix [RENAMED] `\n"
            "This will add `[RENAMED] ` before your filename."
        )
        return
    
    user_id = message.from_user.id
    prefix = " ".join(message.command[1:])
    
    if len(prefix) > 50:
        await message.reply_text("❌ Prefix too long! Maximum 50 characters.")
        return
    
    set_user_prefix(user_id, prefix)
    await message.reply_text(f"✅ Prefix set to: `{prefix}`")

@app.on_message(filters.command("del_prefix"))
async def del_prefix_command(client, message: Message):
    user_id = message.from_user.id
    
    if delete_user_prefix(user_id):
        await message.reply_text("✅ Prefix deleted successfully!")
    else:
        await message.reply_text("❌ No prefix found to delete!")

@app.on_message(filters.command("view_prefix"))
async def view_prefix_command(client, message: Message):
    user_id = message.from_user.id
    prefix = get_user_prefix(user_id)
    
    if prefix:
        await message.reply_text(f"**Your Current Prefix:** `{prefix}`")
    else:
        await message.reply_text("❌ No prefix set! Use `/set_prefix` to add one.")

# Enhanced download with real-time progress
async def download_with_progress(client, message, file_path, progress_tracker, status_msg):
    """Download with real-time progress updates"""
    last_update_time = time.time()
    
    async def progress_callback(current, total):
        # Throttle updates to avoid spam
        current_time = time.time()
        if current_time - last_update_time >= 2.0:  # Update every 2 seconds
            progress_tracker.update(current)
            try:
                await status_msg.edit_text(
                    progress_tracker.get_progress_text(os.path.basename(file_path)),
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
    
    try:
        download_path = await client.download_media(
            message,
            file_name=file_path,
            progress=progress_callback,
            in_memory=False
        )
        return download_path
    except Exception as e:
        print(f"Download error: {e}")
        return None

# Enhanced upload with real-time progress
async def upload_with_progress(client, chat_id, file_path, file_name, caption, thumb, progress_tracker, status_msg, upload_type="document"):
    """Upload with real-time progress updates"""
    last_update_time = time.time()
    
    async def progress_callback(current, total):
        # Throttle updates to avoid spam
        current_time = time.time()
        if current_time - last_update_time >= 2.0:  # Update every 2 seconds
            progress_tracker.update(current)
            try:
                await status_msg.edit_text(
                    progress_tracker.get_progress_text(os.path.basename(file_path)),
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
    
    try:
        if upload_type == "video":
            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                file_name=file_name,
                caption=caption,
                thumb=thumb,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                progress=progress_callback,
                disable_notification=True
            )
        elif upload_type == "audio":
            message = await client.send_audio(
                chat_id=chat_id,
                audio=file_path,
                file_name=file_name,
                caption=caption,
                thumb=thumb,
                parse_mode=ParseMode.MARKDOWN,
                progress=progress_callback,
                disable_notification=True
            )
        elif upload_type == "photo":
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
                progress=progress_callback,
                disable_notification=True
            )
        return message
    except Exception as e:
        print(f"Upload error: {e}")
        raise

# Enhanced file processing with real-time progress
async def max_process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    download_path = None
    status_msg = None
    
    try:
        # Parse command
        parts = (message.text or message.caption).split(" ", 1)
        if len(parts) < 2:
            await message.reply("❌ **Usage:** `/rename new_filename.ext`")
            return
        
        original_name = parts[1].strip()
        if not original_name or len(original_name) > 255:
            await message.reply("❌ Invalid filename")
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
            await message.reply(f"❌ File too large: {format_size(file_size)}")
            return
        
        # Get user preference
        user_preference = get_user_preference(user_id)
        
        # Start processing
        start_time = time.time()
        status_msg = await message.reply("🚀 **Starting MAX TURBO processing...**")
        
        # Generate file path
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        # DOWNLOAD WITH REAL-TIME PROGRESS
        await status_msg.edit_text("📥 **Starting download with real-time progress...**")
        
        download_tracker = ProgressTracker(user_id, "download", file_size)
        download_start = time.time()
        
        download_path = await download_with_progress(client, target_message, file_path, download_tracker, status_msg)
        
        download_time = time.time() - download_start
        
        if not download_path or not os.path.exists(download_path):
            await status_msg.edit_text("❌ Download failed!")
            return
        
        actual_file_size = os.path.getsize(download_path)
        download_speed = actual_file_size / download_time if download_time > 0 else 0
        download_speed_mb = download_speed / (1024 * 1024)
        
        # UPLOAD WITH REAL-TIME PROGRESS
        await status_msg.edit_text("📤 **Starting upload with real-time progress...**")
        
        # Prepare upload parameters
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Max Turbo**")
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Determine upload type
        upload_type = "document"
        if user_preference == "video" and get_file_extension(file_path) in ['.mp4', '.mkv', '.avi', '.mov']:
            upload_type = "video"
        elif get_file_extension(file_path) in ['.mp3', '.m4a', '.flac', '.wav']:
            upload_type = "audio"
        elif get_file_extension(file_path) in ['.jpg', '.jpeg', '.png', '.webp']:
            upload_type = "photo"
        
        upload_tracker = ProgressTracker(user_id, "upload", actual_file_size)
        upload_start = time.time()
        
        sent_message = await upload_with_progress(
            client, target_message.chat.id, file_path, new_name, 
            user_caption, thumbnail_path, upload_tracker, status_msg, upload_type
        )
        
        upload_time = time.time() - upload_start
        upload_speed = actual_file_size / upload_time if upload_time > 0 else 0
        upload_speed_mb = upload_speed / (1024 * 1024)
        
        total_time = time.time() - start_time
        
        # Final completion message
        speed_emoji = "⚡" if download_speed_mb > 50 or upload_speed_mb > 50 else "🚀"
        
        await status_msg.edit_text(
            f"✅ **MAX TURBO COMPLETE!** {speed_emoji}\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"⏱️ **Total Time:** {format_duration(int(total_time))}\n"
            f"📥 **Download:** {format_speed(download_speed)} ({download_speed_mb:.1f} MB/s)\n"
            f"📤 **Upload:** {format_speed(upload_speed)} ({upload_speed_mb:.1f} MB/s)\n"
            f"🔧 **With Prefix:** {'✅' if user_prefix else '❌'}\n"
            f"💾 **Large File:** {'✅' if actual_file_size > 100 * 1024 * 1024 else '❌'}"
        )
        
    except FloodWait as e:
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
        # Cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass
        gc.collect()

# Rename command
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    
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
    mark_message_processed(message.id)
    
    try:
        await max_process_file_rename(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply(f"❌ Processing error: {str(e)}")
    finally:
        set_user_processing(user_id, False)

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Status", callback_data="status")],
        [InlineKeyboardButton("🚀 Upload Mode", callback_data="upload_options")],
        [InlineKeyboardButton("🔧 Prefix", callback_data="prefix_options")]
    ])
    
    await message.reply_text(
        "⚡ **MAX TURBO BOT**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        "**Features:**\n"
        "• 🚀 Real-time progress tracking\n"
        "• 📊 Live ETA, Speed, Time, Size\n"
        "• 🔧 Custom filename prefixes\n"
        "• 💨 Maximum speed optimization\n"
        "• 📁 Up to 4GB file support\n\n"
        "**Commands:**\n"
        "• `/rename` - Rename files\n"
        "• `/set_prefix` - Add filename prefix\n"
        "• `/del_prefix` - Remove prefix\n"
        "• `/view_prefix` - Check current prefix\n"
        "• `/upload_mode` - Set upload preferences\n\n"
        "**⚡ REAL-TIME PROGRESS TRACKING! ⚡**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Status command
@app.on_message(filters.command("status"))
async def status_command(client, message: Message):
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    cpu_percent = psutil.cpu_percent()
    
    await message.reply_text(
        f"⚡ **BOT STATUS**\n\n"
        f"• 💾 **Memory:** {memory_usage:.0f} MB\n"
        f"• 🔥 **CPU:** {cpu_percent}%\n"
        f"• 📁 **Max Size:** {format_size(MAX_FILE_SIZE)}\n"
        f"• 🕒 **Uptime:** {format_duration(time.time() - bot_start_time)}\n\n"
        f"**Features:** Real-time progress • Prefix support • Max speed"
    )

# Callback handlers
@app.on_callback_query(filters.regex("status"))
async def status_callback(client, callback_query):
    await callback_query.answer()
    await status_command(client, callback_query.message)

@app.on_callback_query(filters.regex("prefix_options"))
async def prefix_options_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    current_prefix = get_user_prefix(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Set Prefix", callback_data="set_prefix_dialog")],
        [InlineKeyboardButton("🗑️ Delete Prefix", callback_data="delete_prefix")],
        [InlineKeyboardButton("👀 View Prefix", callback_data="view_prefix")]
    ])
    
    text = "🔧 **Prefix Management**\n\n"
    if current_prefix:
        text += f"**Current Prefix:** `{current_prefix}`\n\n"
    else:
        text += "**No prefix set**\n\n"
    
    text += "Use buttons below to manage your filename prefix."
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("set_prefix_dialog"))
async def set_prefix_dialog(client, callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "📝 **Set Prefix**\n\n"
        "Send me your prefix using:\n"
        "`/set_prefix your_prefix`\n\n"
        "**Example:** `/set_prefix [RENAMED] `\n"
        "This will add `[RENAMED] ` before your filename."
    )

@app.on_callback_query(filters.regex("delete_prefix"))
async def delete_prefix_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if delete_user_prefix(user_id):
        await callback_query.answer("✅ Prefix deleted!")
        await callback_query.message.edit_text("✅ **Prefix deleted successfully!**")
    else:
        await callback_query.answer("❌ No prefix found!")
        await callback_query.message.edit_text("❌ **No prefix found to delete!**")

@app.on_callback_query(filters.regex("view_prefix"))
async def view_prefix_callback(client, callback_query):
    user_id = callback_query.from_user.id
    prefix = get_user_prefix(user_id)
    
    if prefix:
        await callback_query.answer("Current prefix shown")
        await callback_query.message.edit_text(f"**Your Current Prefix:** `{prefix}`")
    else:
        await callback_query.answer("No prefix set")
        await callback_query.message.edit_text("❌ **No prefix set!**\nUse `/set_prefix` to add one.")

# Upload mode command (simplified)
@app.on_message(filters.command("upload_mode"))
async def upload_mode_command(client, message: Message):
    user_id = message.from_user.id
    current_mode = user_upload_preferences.get(str(user_id), "auto")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto", callback_data="mode_auto")],
        [InlineKeyboardButton("📄 Document", callback_data="mode_document")],
    ])
    
    await message.reply_text(
        f"🚀 **Upload Mode:** `{current_mode.upper()}`\n\n"
        "Choose upload method:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("mode_auto"))
async def set_mode_auto(client, callback_query):
    user_id = callback_query.from_user.id
    user_upload_preferences[str(user_id)] = "auto"
    await callback_query.answer("🤖 Auto mode")
    await callback_query.message.edit_text("✅ **Mode:** `AUTO`")

@app.on_callback_query(filters.regex("mode_document"))
async def set_mode_document(client, callback_query):
    user_id = callback_query.from_user.id
    user_upload_preferences[str(user_id)] = "document"
    await callback_query.answer("📄 Document mode")
    await callback_query.message.edit_text("✅ **Mode:** `DOCUMENT`")

@app.on_callback_query(filters.regex("upload_options"))
async def upload_options_callback(client, callback_query):
    await callback_query.answer()
    await upload_mode_command(client, callback_query.message)

# Start the bot
if __name__ == "__main__":
    print("""
⚡ STARTING MAX TURBO BOT...
💨 REAL-TIME FEATURES:
• 📊 Live progress tracking
• ⏱️ Real-time ETA
• 🚀 Speed monitoring
• 🔧 Prefix support
• 📁 Up to 4GB files
    """)
    
    # Load prefixes into memory
    prefixes_data = load_json(PREFIX_DB)
    user_prefixes.update(prefixes_data)
    
    print(f"📁 Max File Size: {format_size(MAX_FILE_SIZE)}")
    print(f"🔧 Loaded {len(user_prefixes)} user prefixes")
    
    start_web_server()
    
    print("🌐 Starting MAX TURBO bot with real-time progress...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Startup error: {e}")
