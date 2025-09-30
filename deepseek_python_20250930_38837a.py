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
from pyrogram.errors import FloodWait, RPCError, ChannelInvalid, ChannelPrivate, PeerIdInvalid
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
# Channel configuration for storage
STORAGE_CHANNEL = os.getenv("STORAGE_CHANNEL", "")  # Your channel username or ID

# ULTRA SPEED SETTINGS
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
CHUNK_SIZE = 512 * 1024  # 512KB
MAX_WORKERS = 200
BUFFER_SIZE = 64 * 1024  # 64KB BUFFER

# Render detection
RENDER = os.getenv('RENDER', '').lower() == 'true'
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')
PORT = int(os.getenv('PORT', 5000))

if not BOT_TOKEN or not API_ID or not API_HASH:
    print("❌ Missing environment variables")
    sys.exit(1)

if not STORAGE_CHANNEL:
    print("❌ STORAGE_CHANNEL not set in environment variables")
    print("💡 Add STORAGE_CHANNEL=@your_channel_username to .env file")
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
FILE_MAPPING_DB = "file_mappings.json"

# Ensure directories
for directory in ["thumbnails", "temp"]:
    os.makedirs(directory, exist_ok=True)

def initialize_json_files():
    files_to_create = {
        USER_DB: {},
        THUMBNAIL_DB: {},
        CAPTION_DB: {},
        PREFIX_DB: {},
        PREFERENCES_DB: {},
        FILE_MAPPING_DB: {},
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
    return jsonify({"status": "online", "bot": "ULTRA FAST BOT", "storage": "TELEGRAM CHANNEL"})

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

# CHANNEL ACCESS VERIFICATION - FIXED
async def verify_channel_access(client):
    """Verify bot has access to the storage channel"""
    try:
        print(f"🔍 Testing access to channel: {STORAGE_CHANNEL}")
        
        # Try to get channel information
        try:
            channel = await client.get_chat(STORAGE_CHANNEL)
            print(f"✅ Channel found: {channel.title} (ID: {channel.id})")
        except (ChannelInvalid, ChannelPrivate, PeerIdInvalid) as e:
            print(f"❌ Channel access error: {e}")
            return False
        
        # Try to send a test message
        try:
            test_message = await client.send_message(
                STORAGE_CHANNEL,
                "🤖 **Bot Connection Test**\n\nThis is a test message to verify channel access.",
                disable_notification=True
            )
            print(f"✅ Test message sent successfully! Message ID: {test_message.id}")
            
            # Try to delete the test message
            try:
                await client.delete_messages(STORAGE_CHANNEL, test_message.id)
                print("✅ Test message cleaned up")
            except:
                print("⚠️ Could not delete test message (normal for some channels)")
            
            return True
            
        except Exception as e:
            print(f"❌ Cannot send messages to channel: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Channel verification failed: {e}")
        return False

# SIMPLE CHANNEL STORAGE - FIXED
async def save_to_channel_simple(client, file_path, file_name):
    """Simple and reliable file upload to channel"""
    try:
        print(f"💾 Attempting to save: {file_name} to {STORAGE_CHANNEL}")
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return None

        file_size = os.path.getsize(file_path)
        print(f"📦 File size: {format_size(file_size)}")

        # Get file extension
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # SIMPLE UPLOAD - Just use send_document for everything
        # This is more reliable than trying to detect file types
        try:
            message = await client.send_document(
                chat_id=STORAGE_CHANNEL,
                document=file_path,
                file_name=file_name,
                caption=f"📁 {file_name}\n💾 Stored by Rename Bot\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                disable_notification=True
            )
            print(f"✅ File saved successfully! Message ID: {message.id}")
            return message.id
            
        except FloodWait as e:
            print(f"⏳ Flood wait: {e.value}s")
            await asyncio.sleep(e.value)
            return await save_to_channel_simple(client, file_path, file_name)
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            # Try alternative method
            return await save_to_channel_alternative(client, file_path, file_name)

    except Exception as e:
        print(f"❌ Error in save_to_channel_simple: {e}")
        return None

async def save_to_channel_alternative(client, file_path, file_name):
    """Alternative method if simple upload fails"""
    try:
        print(f"🔄 Trying alternative upload method for: {file_name}")
        
        # Try without file_name parameter
        message = await client.send_document(
            chat_id=STORAGE_CHANNEL,
            document=file_path,
            disable_notification=True
        )
        print(f"✅ Alternative upload successful! Message ID: {message.id}")
        return message.id
        
    except Exception as e:
        print(f"❌ Alternative upload also failed: {e}")
        return None

# FIXED FORWARD FUNCTION
async def forward_from_channel_simple(client, channel_message_id, chat_id, file_name, caption):
    """Simple forwarding from channel"""
    try:
        print(f"📤 Forwarding message {channel_message_id} to user {chat_id}")
        
        # Use copy_message instead of send_document for better reliability
        copied_message = await client.copy_message(
            chat_id=chat_id,
            from_chat_id=STORAGE_CHANNEL,
            message_id=channel_message_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
        
        print(f"✅ Forwarding successful! New message ID: {copied_message.id}")
        return copied_message
        
    except FloodWait as e:
        print(f"⏳ Flood wait during forward: {e.value}s")
        await asyncio.sleep(e.value)
        return await forward_from_channel_simple(client, channel_message_id, chat_id, file_name, caption)
    except Exception as e:
        print(f"❌ Forwarding failed: {e}")
        raise

# TELEGRAM CHANNEL STORAGE FUNCTIONS
def save_file_mapping(file_hash, channel_message_id):
    mappings = load_json(FILE_MAPPING_DB)
    mappings[file_hash] = channel_message_id
    return save_json(FILE_MAPPING_DB, mappings)

def get_file_mapping(file_hash):
    mappings = load_json(FILE_MAPPING_DB)
    return mappings.get(file_hash)

# THUMBNAIL MANAGEMENT FUNCTIONS
def get_user_thumbnail(user_id):
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnail_path = thumbnails.get(str(user_id))
    if thumbnail_path and os.path.exists(thumbnail_path):
        return thumbnail_path
    return None

def set_user_thumbnail(user_id, thumbnail_path):
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnails[str(user_id)] = thumbnail_path
    return save_json(THUMBNAIL_DB, thumbnails)

def delete_user_thumbnail(user_id):
    thumbnails = load_json(THUMBNAIL_DB)
    user_id_str = str(user_id)
    if user_id_str in thumbnails:
        thumbnail_path = thumbnails[user_id_str]
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except:
                pass
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

# SIMPLIFIED FILE PROCESSING - FIXED
async def ultra_fast_process_file(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    download_path = None
    status_msg = None
    
    try:
        # Parse the rename command
        if message.text.startswith('/rename'):
            parts = message.text.split(" ", 1)
            if len(parts) < 2:
                await message.reply_text("❌ Usage: `/rename new_filename.ext`")
                return
            original_name = parts[1].strip()
        else:
            await message.reply_text("❌ Invalid command format")
            return
        
        if not original_name or len(original_name) > 255:
            await message.reply_text("❌ Invalid filename (1-255 characters)")
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
        elif target_message.photo:
            file_size = target_message.photo.file_size or 0
        else:
            await message.reply_text("❌ Unsupported file type")
            return
        
        if file_size == 0:
            await message.reply_text("❌ Cannot get file size")
            return
            
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large: {format_size(file_size)}")
            return
        
        # Start processing
        start_time = time.time()
        status_msg = await message.reply_text("⚡ **STARTING FILE PROCESSING...**")
        
        # Generate unique file hash
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}_{new_name}".encode()).hexdigest()[:16]
        
        # Check if file already exists in channel storage
        existing_message_id = get_file_mapping(file_hash)
        if existing_message_id:
            await status_msg.edit_text("🔄 **File found in storage, retrieving...**")
            channel_message_id = existing_message_id
            storage_status = "🔄 FROM EXISTING"
        else:
            # STEP 1: Download file temporarily
            temp_path = f"temp/{file_hash}_{new_name}"
            
            await status_msg.edit_text("📥 **DOWNLOADING FILE...**")
            download_start = time.time()
            download_path = await ultra_fast_download(client, target_message, temp_path, None)  # No progress for simplicity
            download_time = time.time() - download_start
            
            if not download_path or not os.path.exists(download_path):
                await status_msg.edit_text("❌ Download failed! File not found.")
                return
            
            # STEP 2: Save to Telegram Channel Storage
            await status_msg.edit_text("💾 **SAVING TO CHANNEL STORAGE...**")
            
            storage_start = time.time()
            channel_message_id = await save_to_channel_simple(client, download_path, new_name)
            storage_time = time.time() - storage_start
            
            if not channel_message_id:
                await status_msg.edit_text(
                    "❌ **Failed to save to channel!**\n\n"
                    "**Please check:**\n"
                    "1. Bot is admin in the channel\n"
                    "2. Channel exists: " + STORAGE_CHANNEL + "\n"
                    "3. Bot can send messages\n"
                    "4. Use /setup_channel for help"
                )
                return
            
            # Save file mapping
            save_file_mapping(file_hash, channel_message_id)
            storage_status = "💾 NEW STORAGE"
        
        # STEP 3: Forward from channel to user
        await status_msg.edit_text("📤 **SENDING FILE TO YOU...**")
        
        # Get user caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n💾 **Powered by Telegram Channel Storage**")
        
        upload_start = time.time()
        
        # Forward from channel storage
        try:
            sent_message = await forward_from_channel_simple(
                client, 
                channel_message_id, 
                message.chat.id, 
                new_name, 
                user_caption
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Error sending file: {str(e)}")
            return
        
        upload_time = time.time() - upload_start
        total_time = time.time() - start_time
        
        # Performance calculation
        download_speed = file_size / download_time if download_time > 0 else 0
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        
        await status_msg.edit_text(
            f"✅ **FILE PROCESSING COMPLETE!**\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(file_size)}\n"
            f"⏱ **Total Time:** {format_duration(total_time)}\n"
            f"💾 **Storage:** {storage_status}\n"
            f"🏷️ **Prefix:** {'✅' if user_prefix else '❌'}\n\n"
            f"**Status:** 💾 **TELEGRAM CHANNEL STORAGE ACTIVE**"
        )
        
        # Update stats
        stats = load_json(STATS_DB)
        stats["total_files"] = stats.get("total_files", 0) + 1
        save_json(STATS_DB, stats)
        
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
        # Cleanup temporary file
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
                print(f"🧹 Cleaned up temporary file: {download_path}")
            except Exception as e:
                print(f"Cleanup error: {e}")

# FIXED RENAME COMMAND
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if message.id in processed_messages:
        return
    processed_messages.add(message.id)
    
    user_id = message.from_user.id
    
    if user_id in user_processing and user_processing[user_id]:
        await message.reply_text("⏳ Please wait, processing your previous file...")
        return
    
    if not message.reply_to_message:
        await message.reply_text(
            "❌ **How to use:**\n"
            "1. Reply to a file with `/rename new_filename.ext`\n"
            "2. Wait for processing\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Storage:** 💾 **TELEGRAM CHANNEL**"
        )
        return
    
    if not message.reply_to_message.media:
        await message.reply_text("❌ Please reply to a media file")
        return
    
    user_processing[user_id] = True
    
    try:
        await ultra_fast_process_file(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply_text(f"❌ Processing error: {str(e)}")
    finally:
        user_processing[user_id] = False

# CHANNEL SETUP COMMAND - FIXED
@app.on_message(filters.command("setup_channel"))
async def setup_channel_command(client, message: Message):
    """Help user setup the channel properly"""
    help_text = f"""
🔧 **CHANNEL SETUP GUIDE**

**Current Channel:** `{STORAGE_CHANNEL}`

**Step-by-Step Setup:**

1. **Create a Telegram Channel**
   - Go to Telegram → New Channel
   - Give it a name (e.g., "My File Storage")
   - Make it **Public** (recommended) or **Private**

2. **Add Bot as Admin**
   - Go to Channel → Edit → Administrators
   - Add @{(await client.get_me()).username} as admin
   - Grant these permissions:
     ✅ Post Messages
     ✅ Edit Messages  
     ✅ Delete Messages

3. **Get Channel Info**
   - For public channels: Use @username (e.g., @myfiles)
   - For private channels: Use channel ID (e.g., -100123456789)

4. **Update .env File**