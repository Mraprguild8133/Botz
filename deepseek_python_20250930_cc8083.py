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

# Render environment detection
RENDER = os.getenv('RENDER', '').lower() == 'true'
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')
RENDER_INSTANCE_ID = os.getenv('RENDER_INSTANCE_ID', '')
PORT = int(os.getenv('PORT', 5000))

# Validate required environment variables
if not BOT_TOKEN or not API_ID or not API_HASH:
    print("❌ Error: BOT_TOKEN, API_ID, and API_HASH must be set in .env file")
    sys.exit(1)

# Bot settings
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB

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
        # Get system info
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        cpu_percent = psutil.cpu_percent()
        disk_usage = psutil.disk_usage('.').percent
        
        # Get bot stats
        stats = load_json(STATS_DB)
        users = load_json(USER_DB)
        
        # Calculate uptime
        uptime_seconds = int(time.time() - bot_start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        
        return jsonify({
            "status": "online",
            "bot_name": "File Rename Bot",
            "deployment": "render" if RENDER else "local",
            "web_server": "running",
            "web_url": web_server_url,
            "instance_id": RENDER_INSTANCE_ID,
            "port": PORT,
            "uptime": uptime_str,
            "memory_usage_mb": round(memory_usage, 2),
            "cpu_usage_percent": cpu_percent,
            "disk_usage_percent": disk_usage,
            "total_users": len(users),
            "total_files_processed": stats.get("total_files", 0),
            "max_file_size": format_size(MAX_FILE_SIZE),
            "bot_start_time": stats.get("bot_start_time"),
            "last_restart": stats.get("last_restart"),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app_web.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Check essential services
        services = {
            "web_server": True,
            "environment_variables": bool(BOT_TOKEN and API_ID and API_HASH),
            "storage_files": all(os.path.exists(f) for f in [USER_DB, STATS_DB]),
            "disk_space": psutil.disk_usage('.').free > 100 * 1024 * 1024,  # 100MB free
            "deployment": "render" if RENDER else "local"
        }
        
        health_status = "healthy" if all(services.values()) else "degraded"
        
        return jsonify({
            "status": health_status,
            "services": services,
            "deployment_info": {
                "on_render": RENDER,
                "external_url": RENDER_EXTERNAL_URL,
                "instance_id": RENDER_INSTANCE_ID,
                "port": PORT
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app_web.route('/status')
def detailed_status():
    """Detailed status page"""
    try:
        stats = load_json(STATS_DB)
        users = load_json(USER_DB)
        
        # Calculate active users (last 24 hours)
        active_users = 0
        twenty_four_hours_ago = datetime.now().timestamp() - 86400
        for user_data in users.values():
            last_active = datetime.fromisoformat(user_data.get("last_active", "2000-01-01")).timestamp()
            if last_active > twenty_four_hours_ago:
                active_users += 1
        
        return jsonify({
            "bot": {
                "uptime_seconds": int(time.time() - bot_start_time),
                "start_time": stats.get("bot_start_time"),
                "deployment": stats.get("deployment_type", "unknown")
            },
            "system": {
                "memory_usage_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 2),
                "cpu_usage_percent": psutil.cpu_percent(),
                "disk_usage_percent": psutil.disk_usage('.').percent
            },
            "users": {
                "total": len(users),
                "active_24h": active_users,
                "files_processed": stats.get("total_files", 0)
            },
            "deployment": {
                "on_render": RENDER,
                "external_url": RENDER_EXTERNAL_URL,
                "instance_id": RENDER_INSTANCE_ID,
                "port": PORT,
                "web_url": web_server_url
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app_web.route('/render')
def render_info():
    """Render-specific information"""
    try:
        return jsonify({
            "deployment": {
                "platform": "render" if RENDER else "local",
                "external_url": RENDER_EXTERNAL_URL,
                "instance_id": RENDER_INSTANCE_ID,
                "port": PORT,
                "detected": RENDER,
                "web_server_url": web_server_url
            },
            "environment": {
                "RENDER": os.getenv('RENDER', 'not set'),
                "PORT": os.getenv('PORT', 'not set'),
                "RENDER_EXTERNAL_URL": os.getenv('RENDER_EXTERNAL_URL', 'not set'),
                "RENDER_INSTANCE_ID": os.getenv('RENDER_INSTANCE_ID', 'not set')
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app_web.route('/users')
def users_info():
    """Users information endpoint"""
    try:
        users = load_json(USER_DB)
        user_list = []
        
        for user_id, user_data in users.items():
            if user_id == "example":
                continue
            user_list.append({
                "user_id": user_id,
                "joined_at": user_data.get("joined_at"),
                "last_active": user_data.get("last_active"),
                "files_processed": user_data.get("files_processed", 0)
            })
        
        return jsonify({
            "total_users": len(user_list),
            "deployment": "render" if RENDER else "local",
            "users": user_list
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_web_server():
    """Run the Flask web server with Render detection"""
    global web_server_started, web_server_url
    
    try:
        # Determine host and port based on environment
        host = '0.0.0.0'  # Always bind to all interfaces
        
        if RENDER:
            print(f"🚀 Render Environment Detected")
            print(f"🌐 External URL: {RENDER_EXTERNAL_URL}")
            print(f"🆔 Instance ID: {RENDER_INSTANCE_ID}")
            print(f"🔌 Using PORT: {PORT}")
            web_server_url = RENDER_EXTERNAL_URL
        else:
            print(f"💻 Local Development Environment")
            print(f"🌐 Web Server will be available on port {PORT}")
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

# Initialize Pyrogram Client
try:
    app = Client(
        "file_rename_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=30,
        workers=100,
        in_memory=False
    )
    print("✅ Pyrogram client initialized successfully")
except Exception as e:
    print(f"❌ Error initializing Pyrogram client: {e}")
    sys.exit(1)

# Start command with enhanced status
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    save_user(user_id)
    update_user_activity(user_id)
    
    # Get status
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    deployment_type = "🚀 Render" if RENDER else "💻 Local"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Status", callback_data="bot_status")],
        [InlineKeyboardButton("🔧 Prefix Settings", callback_data="prefix_settings")],
        [InlineKeyboardButton("📁 Upload Mode", callback_data="upload_mode")],
        [InlineKeyboardButton("🌐 Web Dashboard", url=web_server_url)],
        [InlineKeyboardButton("💾 File Limits", callback_data="file_limits")]
    ])
    
    await message.reply_text(
        f"🤖 **File Rename Bot**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        f"**System Status:**\n"
        f"• 🌐 Web Server: {web_status}\n"
        f"• 🚀 Deployment: {deployment_type}\n"
        f"• 🕒 Uptime: {get_uptime()}\n\n"
        "**Available Commands:**\n"
        "• `/rename` - Rename files\n"
        "• `/set_prefix` - Add filename prefix\n"
        "• `/del_prefix` - Remove prefix\n"
        "• `/view_prefix` - Check prefix\n"
        "• `/set_caption` - Set custom caption\n"
        "• `/see_caption` - View caption\n"
        "• `/del_caption` - Delete caption\n"
        "• `/view_thumb` - View thumbnail\n"
        "• `/upload_mode` - Set upload preferences\n"
        "• `/status` - Detailed bot status\n\n"
        f"**Web Dashboard:** {web_server_url}\n\n"
        "**Send a photo to set as thumbnail!**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Enhanced status command
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
    disk_usage = psutil.disk_usage('.').percent
    
    # Status
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    deployment_type = "🚀 Render" if RENDER else "💻 Local"
    
    await message.reply_text(
        f"📊 **Bot Status Dashboard**\n\n"
        f"**System Status:**\n"
        f"• 🌐 Web Server: {web_status}\n"
        f"• 🚀 Deployment: {deployment_type}\n\n"
        f"**Statistics:**\n"
        f"• 👥 Total Users: {total_users}\n"
        f"• 📁 Files Processed: {total_files}\n"
        f"• 🚀 Max File Size: {format_size(MAX_FILE_SIZE)}\n"
        f"• 🕒 Uptime: {get_uptime()}\n\n"
        f"**System Resources:**\n"
        f"• 💾 Memory: {memory_usage:.2f} MB\n"
        f"• 🔥 CPU: {cpu_percent}%\n"
        f"• 💽 Disk: {disk_usage}%\n\n"
        f"**Web Dashboard:** {web_server_url}",
        parse_mode=ParseMode.MARKDOWN
    )

# Rename command
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if is_user_processing(user_id):
        await message.reply_text("⏳ Please wait! You're already processing a file.")
        return
    
    if not message.reply_to_message:
        await message.reply_text(
            "**Usage:** Reply to a file with:\n"
            "`/rename new_filename.ext`\n\n"
            f"**Max File Size:** {format_size(MAX_FILE_SIZE)}"
        )
        return
    
    replied_message = message.reply_to_message
    
    if not replied_message.media:
        await message.reply_text("❌ Please reply to a file (document, video, audio, or photo)")
        return
    
    set_user_processing(user_id, True)
    
    try:
        await process_file_rename(client, message, replied_message)
    except Exception as e:
        logger.error(f"Rename error: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        set_user_processing(user_id, False)

async def process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    status_msg = None
    download_path = None
    
    try:
        # Extract new file name
        parts = message.text.split(" ", 1)
        if len(parts) < 2:
            await message.reply_text("❌ Please provide a new file name!\nExample: `/rename my_file.pdf`")
            return
        
        original_name = parts[1].strip()
        if not original_name or len(original_name) > 255:
            await message.reply_text("❌ Invalid file name! Must be 1-255 characters.")
            return
        
        # Apply prefix
        user_prefix = get_user_prefix(user_id)
        new_name = user_prefix + original_name
        
        # Check file size
        file_size = 0
        if target_message.document:
            file_size = target_message.document.file_size or 0
        elif target_message.video:
            file_size = target_message.video.file_size or 0
        elif target_message.audio:
            file_size = target_message.audio.file_size or 0
        elif target_message.photo:
            file_size = 20 * 1024 * 1024  # Estimate for photos
        
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large! {format_size(file_size)} > {format_size(MAX_FILE_SIZE)}")
            return
        
        # Start processing
        start_time = time.time()
        status_msg = await message.reply_text(f"🚀 Processing: {new_name}...")
        
        # Download file
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        await status_msg.edit_text("📥 Downloading file...")
        download_path = await client.download_media(target_message, file_name=file_path)
        
        if not download_path or not os.path.exists(download_path):
            await status_msg.edit_text("❌ Download failed!")
            return
        
        actual_file_size = os.path.getsize(download_path)
        
        # Prepare caption and thumbnail
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**")
        
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Upload file
        await status_msg.edit_text("📤 Uploading file...")
        
        user_preference = get_user_preference(user_id)
        
        if target_message.document or user_preference == "document":
            await client.send_document(
                chat_id=message.chat.id,
                document=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif target_message.video and user_preference != "document":
            await client.send_video(
                chat_id=message.chat.id,
                video=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True
            )
        elif target_message.audio:
            await client.send_audio(
                chat_id=message.chat.id,
                audio=download_path,
                file_name=new_name,
                caption=user_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif target_message.photo:
            await client.send_photo(
                chat_id=message.chat.id,
                photo=download_path,
                caption=user_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Update stats
        users = load_json(USER_DB)
        if str(user_id) in users:
            users[str(user_id)]["files_processed"] = users[str(user_id)].get("files_processed", 0) + 1
            save_json(USER_DB, users)
        
        update_stats(files_processed=1)
        
        total_time = time.time() - start_time
        
        await status_msg.edit_text(
            f"✅ **File Renamed Successfully!**\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(actual_file_size)}\n"
            f"⏱ **Time:** {format_duration(int(total_time))}\n"
            f"🔧 **Prefix:** {'✅' if user_prefix else '❌'}"
        )
        
    except Exception as e:
        error_msg = f"❌ Processing Error: {str(e)}"
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
        logger.error(f"File processing error: {e}")
    
    finally:
        # Cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass

# Prefix commands
@app.on_message(filters.command("set_prefix"))
async def set_prefix_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/set_prefix your_prefix`\n\n"
            "**Example:** `/set_prefix [RENAMED] `\n"
            "This will add `[RENAMED] ` before your filename."
        )
        return
    
    prefix = " ".join(message.command[1:])
    
    if len(prefix) > 50:
        await message.reply_text("❌ Prefix too long! Maximum 50 characters.")
        return
    
    if set_user_prefix(user_id, prefix):
        await message.reply_text(f"✅ Prefix set to: `{prefix}`")
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
        await message.reply_text("✅ Prefix deleted successfully!")
    else:
        await message.reply_text("❌ No prefix found to delete!")

@app.on_message(filters.command("view_prefix"))
async def view_prefix_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    prefix = get_user_prefix(user_id)
    
    if prefix:
        await message.reply_text(f"**Your Current Prefix:** `{prefix}`")
    else:
        await message.reply_text("❌ No prefix set! Use `/set_prefix` to add one.")

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
        await message.reply_photo(thumbnail_file, caption="📸 **Your Current Thumbnail**")
    else:
        await message.reply_text("❌ **No thumbnail found!**\nSend an image as photo to set thumbnail.")

@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumb_path = f"thumbnails/{user_id}_{int(time.time())}.jpg"
    
    status_msg = await message.reply_text("📥 Downloading thumbnail...")
    try:
        await message.download(thumb_path)
        
        thumbnails = load_json(THUMBNAIL_DB)
        # Remove old thumbnail if exists
        old_thumb = thumbnails.get(str(user_id))
        if old_thumb and os.path.exists(old_thumb):
            try:
                os.remove(old_thumb)
            except:
                pass
        
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        
        await status_msg.edit_text("✅ **Thumbnail set successfully!**")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error setting thumbnail:** {str(e)}")

# Caption commands
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
            "**Example:**\n`/set_caption 📁 {filename} | Size: {size}`"
        )
        return
    
    custom_caption = " ".join(message.command[1:])
    
    captions = load_json(CAPTION_DB)
    captions[str(user_id)] = custom_caption
    save_json(CAPTION_DB, captions)
    
    await message.reply_text("✅ **Custom caption set successfully!**")

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

# Upload mode command
@app.on_message(filters.command("upload_mode"))
async def upload_mode_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    current_mode = get_user_preference(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto Detect", callback_data="mode_auto")],
        [InlineKeyboardButton("📄 Force Document", callback_data="mode_document")],
    ])
    
    await message.reply_text(
        f"📁 **Upload Mode Settings**\n\n"
        f"**Current Mode:** `{current_mode.upper()}`\n\n"
        "**Options:**\n"
        "• **Auto Detect** - Smart detection based on file type\n"
        "• **Force Document** - Always upload as document\n\n"
        "Choose your preferred upload mode:",
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
        f"📊 **Max File Size:** {format_size(MAX_FILE_SIZE)}\n\n"
        "⚡ **All features working properly!**",
        parse_mode=ParseMode.MARKDOWN
    )

# Callback query handlers
@app.on_callback_query(filters.regex("bot_status"))
async def bot_status_callback(client, callback_query):
    await callback_query.answer()
    await status_command(client, callback_query.message)

@app.on_callback_query(filters.regex("prefix_settings"))
async def prefix_settings_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    prefix = get_user_prefix(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Set Prefix", callback_data="set_prefix_dialog")],
        [InlineKeyboardButton("🗑️ Delete Prefix", callback_data="delete_prefix")],
        [InlineKeyboardButton("👀 View Prefix", callback_data="view_prefix_cb")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    
    text = "🔧 **Prefix Management**\n\n"
    if prefix:
        text += f"**Current Prefix:** `{prefix}`\n\n"
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

@app.on_callback_query(filters.regex("view_prefix_cb"))
async def view_prefix_callback(client, callback_query):
    user_id = callback_query.from_user.id
    prefix = get_user_prefix(user_id)
    
    if prefix:
        await callback_query.answer("Current prefix shown")
        await callback_query.message.edit_text(f"**Your Current Prefix:** `{prefix}`")
    else:
        await callback_query.answer("No prefix set")
        await callback_query.message.edit_text("❌ **No prefix set!**\nUse `/set_prefix` to add one.")

@app.on_callback_query(filters.regex("upload_mode"))
async def upload_mode_callback(client, callback_query):
    await callback_query.answer()
    await upload_mode_command(client, callback_query.message)

@app.on_callback_query(filters.regex("mode_auto"))
async def set_mode_auto(client, callback_query):
    user_id = callback_query.from_user.id
    set_user_preference(user_id, "auto")
    await callback_query.answer("🤖 Auto mode activated!")
    await callback_query.message.edit_text("✅ **Upload Mode Set to:** `AUTO`\n\nFiles will be automatically detected and uploaded accordingly.")

@app.on_callback_query(filters.regex("mode_document"))
async def set_mode_document(client, callback_query):
    user_id = callback_query.from_user.id
    set_user_preference(user_id, "document")
    await callback_query.answer("📄 Document mode activated!")
    await callback_query.message.edit_text("✅ **Upload Mode Set to:** `DOCUMENT`\n\nAll files will be uploaded as documents.")

@app.on_callback_query(filters.regex("file_limits"))
async def file_limits_callback(client, callback_query):
    await callback_query.answer()
    await file_limits_command(client, callback_query.message)

@app.on_callback_query(filters.regex("back_to_main"))
async def back_to_main(client, callback_query):
    await callback_query.answer()
    await start_command(client, callback_query.message)

# Start the bot with web server
if __name__ == "__main__":
    print("🤖 STARTING FILE RENAME BOT...")
    print(f"📁 Max File Size: {format_size(MAX_FILE_SIZE)}")
    
    # Detect environment
    if RENDER:
        print("🚀 **RENDER DEPLOYMENT DETECTED**")
        print(f"🌐 External URL: {RENDER_EXTERNAL_URL}")
        print(f"🆔 Instance ID: {RENDER_INSTANCE_ID}")
        print(f"🔌 Port: {PORT}")
    else:
        print("💻 **LOCAL DEVELOPMENT ENVIRONMENT**")
        print(f"🔌 Port: {PORT}")
    
    # Start web server
    start_web_server()
    
    # Wait a moment for web server to start
    time.sleep(2)
    
    print(f"\n🌐 Web Server URLs:")
    print(f"   📊 Status: {web_server_url}")
    print(f"   ❤️ Health: {web_server_url}/health")
    print(f"   📈 Detailed: {web_server_url}/status")
    print(f"   🚀 Render Info: {web_server_url}/render")
    print(f"   👥 Users: {web_server_url}/users")
    
    print("\n✅ All systems starting...")
    print("🚀 Bot is ready to use...")
    
    try:
        app.run()
    except Exception as e:
        print(f"❌ Bot startup error: {e}")