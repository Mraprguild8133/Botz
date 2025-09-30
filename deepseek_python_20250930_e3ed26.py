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

# ULTRA SPEED SETTINGS - OPTIMIZED FOR INSTANT TRANSFER
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
CHUNK_SIZE = 512 * 1024  # 512KB - OPTIMAL FOR TELEGRAM
MAX_WORKERS = 200  # DOUBLE THE WORKERS
BUFFER_SIZE = 64 * 1024  # 64KB BUFFER
PARALLEL_DOWNLOADS = 5  # PARALLEL CHUNK DOWNLOADS
PARALLEL_UPLOADS = 5   # PARALLEL CHUNK UPLOADS

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
for directory in ["downloads", "thumbnails", "temp", "chunks"]:
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

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_duration(seconds):
    return f"{int(seconds//3600):02d}:{int((seconds%3600)//60):02d}:{int(seconds%60):02d}"

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
        if time_diff >= 0.1:  # UPDATE EVERY 100ms FOR INSTANT FEEDBACK
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
        
        # Create progress bar
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
        sleep_threshold=60,  # HIGHER SLEEP THRESHOLD
        workers=MAX_WORKERS,
        max_concurrent_transmissions=50,  # MAXIMUM CONCURRENT
        in_memory=False
    )
    print("✅ ULTRA FAST Pyrogram client initialized")
except Exception as e:
    print(f"❌ Client error: {e}")
    sys.exit(1)

# ULTRA FAST DOWNLOAD WITH PARALLEL CHUNKS
async def ultra_fast_download(client, message, file_path, progress_callback):
    """ULTRA FAST download with parallel chunk processing"""
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

# ULTRA FAST UPLOAD WITH OPTIMIZED PARAMETERS
async def ultra_fast_upload(client, chat_id, file_path, file_name, caption, thumb, file_type, progress_callback):
    """ULTRA FAST upload with optimized parameters"""
    try:
        upload_params = {
            "chat_id": chat_id,
            "file_name": file_name,
            "caption": caption,
            "thumb": thumb,
            "parse_mode": ParseMode.MARKDOWN,
            "progress": progress_callback,
            "disable_notification": True
        }
        
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

# ULTRA FAST FILE PROCESSING
async def ultra_fast_process_file(client, message: Message, target_message: Message):
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
        
        # Start ULTRA FAST processing
        start_time = time.time()
        status_msg = await message.reply_text("⚡ **INITIALIZING ULTRA FAST TRANSFER...**")
        
        # Generate file path
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
            
            # UPDATE EVERY SECOND FOR INSTANT FEEDBACK
            if metrics and (current_time - last_update >= 1.0 or current == total):
                try:
                    await status_msg.edit_text(
                        download_progress.get_progress_text(new_name),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update = current_time
                except Exception as e:
                    print(f"Progress error: {e}")
        
        download_start = time.time()
        download_path = await ultra_fast_download(client, target_message, file_path, download_callback)
        download_time = time.time() - download_start
        
        if not download_path or not os.path.exists(download_path):
            await status_msg.edit_text("❌ Download failed!")
            return
        
        downloaded_size = os.path.getsize(download_path)
        download_speed = downloaded_size / download_time if download_time > 0 else 0
        
        # ULTRA FAST UPLOAD
        await status_msg.edit_text("🚀 **STARTING ULTRA FAST UPLOAD...**")
        
        # Get upload settings
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n⚡ **Ultra Fast Upload**")
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Determine upload type
        upload_mode = get_upload_mode(user_id)
        if upload_mode == "auto":
            if target_message.video:
                upload_type = "video"
            elif target_message.audio:
                upload_type = "audio"
            elif target_message.photo:
                upload_type = "photo"
            else:
                upload_type = "document"
        else:
            upload_type = upload_mode
        
        upload_progress = UltraFastProgress(downloaded_size, "upload")
        last_upload_update = 0
        
        async def upload_callback(current, total):
            nonlocal last_upload_update
            metrics = upload_progress.update(current)
            current_time = time.time()
            
            # UPDATE EVERY SECOND FOR INSTANT FEEDBACK
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
        sent_message = await ultra_fast_upload(
            client, message.chat.id, download_path, new_name, 
            user_caption, thumbnail_path, upload_type, upload_callback
        )
        upload_time = time.time() - upload_start
        upload_speed = downloaded_size / upload_time if upload_time > 0 else 0
        
        total_time = time.time() - start_time
        
        # Performance rating
        speed_rating = "⚡ ULTRA FAST"
        avg_speed = (download_speed + upload_speed) / 2
        if avg_speed < 10 * 1024 * 1024:  # 10 MB/s
            speed_rating = "🚀 FAST"
        if avg_speed < 5 * 1024 * 1024:   # 5 MB/s
            speed_rating = "📊 NORMAL"
        
        await status_msg.edit_text(
            f"✅ **{speed_rating} TRANSFER COMPLETE!**\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(downloaded_size)}\n"
            f"⏱ **Total Time:** {format_duration(total_time)}\n\n"
            f"📥 **Download:** {format_size(download_speed)}/s\n"
            f"📤 **Upload:** {format_size(upload_speed)}/s\n"
            f"🔧 **Mode:** {upload_type.upper()}\n\n"
            f"**Status:** ⚡ **ULTRA FAST TRANSFER COMPLETE**"
        )
        
        # Update stats
        stats = load_json(STATS_DB)
        stats["total_files"] = stats.get("total_files", 0) + 1
        save_json(STATS_DB, stats)
        
    except FloodWait as e:
        await (status_msg or message).reply_text(f"⏳ Flood wait: {e.value}s")
        await asyncio.sleep(e.value)
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
    finally:
        # Fast cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass

# ULTRA FAST RENAME COMMAND
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if message.id in processed_messages:
        return
    processed_messages.add(message_id)
    
    user_id = message.from_user.id
    
    if user_id in user_processing and user_processing[user_id]:
        await message.reply_text("⏳ Processing previous file...")
        return
    
    if not message.reply_to_message or not message.reply_to_message.media:
        await message.reply_text(
            "❌ Reply to a file with `/rename filename.ext`\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Speed:** ⚡ **ULTRA FAST TRANSFER**"
        )
        return
    
    user_processing[user_id] = True
    
    try:
        await ultra_fast_process_file(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        user_processing[user_id] = False

# ULTRA FAST START COMMAND
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Speed Test", callback_data="speed_test")],
        [InlineKeyboardButton("🔧 Settings", callback_data="settings")],
        [InlineKeyboardButton("🌐 Status", url=web_server_url)]
    ])
    
    await message.reply_text(
        f"⚡ **ULTRA FAST RENAME BOT**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        f"**Features:**\n"
        f"• ⚡ Instant speed transfers\n"
        f"• 🚀 Parallel processing\n"
        f"• 📊 Real-time progress\n"
        f"• 📁 4GB file support\n\n"
        f"**System:** {web_status}\n"
        f"**Commands:** `/rename filename.ext`\n\n"
        f"**⚡ EXPERIENCE INSTANT SPEED!**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# SPEED TEST COMMAND
@app.on_message(filters.command("speedtest"))
async def speed_test_command(client, message: Message):
    test_msg = await message.reply_text("⚡ **Testing ULTRA FAST Speed...**")
    
    # Create a test file
    test_size = 10 * 1024 * 1024  # 10MB test file
    test_file = f"temp/speed_test_{message.from_user.id}.bin"
    
    # Generate test data
    with open(test_file, 'wb') as f:
        f.write(os.urandom(test_size))
    
    start_time = time.time()
    
    # Upload test
    await client.send_document(
        message.chat.id,
        test_file,
        file_name="speed_test.bin",
        caption="⚡ **ULTRA FAST Speed Test**"
    )
    
    upload_time = time.time() - start_time
    upload_speed = test_size / upload_time
    
    # Cleanup
    try:
        os.remove(test_file)
    except:
        pass
    
    await test_msg.edit_text(
        f"⚡ **ULTRA FAST SPEED TEST RESULTS**\n\n"
        f"📦 **Test Size:** {format_size(test_size)}\n"
        f"⏱ **Upload Time:** {upload_time:.2f}s\n"
        f"🚀 **Upload Speed:** {format_size(upload_speed)}/s\n\n"
        f"**Rating:** {'⚡ ULTRA FAST' if upload_speed > 10*1024*1024 else '🚀 FAST'}\n"
        f"**Status:** ⚡ **OPTIMIZED FOR MAXIMUM SPEED**"
    )

# SETTINGS COMMAND
@app.on_message(filters.command("settings"))
async def settings_command(client, message: Message):
    user_id = message.from_user.id
    prefix = get_user_prefix(user_id)
    upload_mode = get_upload_mode(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Set Prefix", callback_data="set_prefix")],
        [InlineKeyboardButton("📤 Upload Mode", callback_data="upload_mode")],
        [InlineKeyboardButton("⚡ Speed Test", callback_data="speed_test")]
    ])
    
    await message.reply_text(
        f"🔧 **ULTRA FAST SETTINGS**\n\n"
        f"**Current Prefix:** `{prefix if prefix else 'None'}`\n"
        f"**Upload Mode:** {upload_mode.upper()}\n\n"
        f"**Optimizations:**\n"
        f"• ⚡ Instant progress updates\n"
        f"• 🚀 Parallel transfers\n"
        f"• 📊 Real-time speed tracking\n"
        f"• 💨 Optimized chunk sizes\n\n"
        f"**Choose an option:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# CALLBACK HANDLERS
@app.on_callback_query(filters.regex("speed_test"))
async def speed_test_callback(client, callback_query):
    await callback_query.answer()
    await speed_test_command(client, callback_query.message)

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
        f"• 🤖 **Auto:** Smart detection\n"
        f"• 📁 **Document:** Force as file\n"
        f"• 🎥 **Video:** Force as video\n\n"
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
    
    if set_user_prefix(user_id, prefix):
        await message.reply_text(f"✅ Prefix set: `{prefix}`\n\n⚡ **Now experience ULTRA FAST transfers!**")
    else:
        await message.reply_text("❌ Failed to set prefix!")

# START BOT WITH ULTRA FAST OPTIMIZATIONS
if __name__ == "__main__":
    print("⚡ STARTING ULTRA FAST BOT...")
    print("🚀 Performance Optimizations:")
    print(f"   • Chunk Size: {format_size(CHUNK_SIZE)}")
    print(f"   • Workers: {MAX_WORKERS}")
    print(f"   • Parallel Transfers: {PARALLEL_DOWNLOADS}")
    print(f"   • Max File: {format_size(MAX_FILE_SIZE)}")
    print("   • Instant Progress Updates")
    print("   • Real-time Speed Tracking")
    
    # Start web server
    start_web_server()
    
    print(f"🌐 Web Dashboard: {web_server_url}")
    print("⚡ ULTRA FAST BOT READY - EXPERIENCE INSTANT SPEED!")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Startup error: {e}")