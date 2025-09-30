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
from pyrogram.errors import FloodWait, RPCError, ChannelInvalid, ChannelPrivate
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

# CHANNEL ACCESS VERIFICATION
async def verify_channel_access(client):
    """Verify bot has access to the storage channel"""
    try:
        # Try to get channel information
        channel = await client.get_chat(STORAGE_CHANNEL)
        print(f"✅ Channel access verified: {channel.title}")
        return True
    except ChannelInvalid:
        print(f"❌ Channel Invalid: {STORAGE_CHANNEL}")
        return False
    except ChannelPrivate:
        print(f"❌ Channel Private: {STORAGE_CHANNEL} - Make sure bot is added as admin")
        return False
    except Exception as e:
        print(f"❌ Channel access error: {e}")
        return False

# TELEGRAM CHANNEL STORAGE FUNCTIONS
def save_file_mapping(file_hash, channel_message_id):
    """Save mapping between file hash and channel message ID"""
    mappings = load_json(FILE_MAPPING_DB)
    mappings[file_hash] = channel_message_id
    return save_json(FILE_MAPPING_DB, mappings)

def get_file_mapping(file_hash):
    """Get channel message ID for a file hash"""
    mappings = load_json(FILE_MAPPING_DB)
    return mappings.get(file_hash)

async def save_to_channel(client, file_path, file_name, caption=""):
    """Save file to Telegram channel and return message ID"""
    try:
        # Verify file exists
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return None

        file_size = os.path.getsize(file_path)
        print(f"💾 Saving to channel: {file_name} ({format_size(file_size)})")

        # Determine file type
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # Prepare common parameters
        common_params = {
            "chat_id": STORAGE_CHANNEL,
            "caption": f"📁 {file_name}\n\n{caption}"[:1024],  # Telegram caption limit
            "disable_notification": True
        }

        try:
            if file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                message = await client.send_video(
                    video=file_path,
                    supports_streaming=True,
                    **common_params
                )
            elif file_ext in ['.mp3', '.m4a', '.flac', '.wav', '.ogg']:
                message = await client.send_audio(
                    audio=file_path,
                    **common_params
                )
            elif file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                message = await client.send_photo(
                    photo=file_path,
                    **common_params
                )
            else:
                message = await client.send_document(
                    document=file_path,
                    file_name=file_name,
                    **common_params
                )
            
            print(f"✅ File saved to channel: Message ID {message.id}")
            return message.id
            
        except FloodWait as e:
            print(f"⏳ Flood wait: {e.value}s")
            await asyncio.sleep(e.value)
            return await save_to_channel(client, file_path, file_name, caption)
        except Exception as e:
            print(f"❌ Error sending file: {e}")
            return None

    except Exception as e:
        print(f"❌ Error saving to channel: {e}")
        return None

async def forward_from_channel(client, channel_message_id, chat_id, file_name, caption, file_type, progress_callback):
    """Forward file from channel to user"""
    try:
        upload_params = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": ParseMode.MARKDOWN,
            "progress": progress_callback,
            "disable_notification": True
        }

        # Add file_name for documents
        if file_type != "photo":
            upload_params["file_name"] = file_name

        # Get user thumbnail
        user_id = chat_id
        thumbnail_path = get_user_thumbnail(user_id)
        if thumbnail_path and file_type in ["video", "audio", "document"]:
            upload_params["thumb"] = thumbnail_path

        if file_type == "video":
            message = await client.send_video(
                video=channel_message_id,
                supports_streaming=True,
                **upload_params
            )
        elif file_type == "audio":
            message = await client.send_audio(
                audio=channel_message_id,
                **upload_params
            )
        elif file_type == "photo":
            message = await client.send_photo(
                photo=channel_message_id,
                **upload_params
            )
        else:
            message = await client.send_document(
                document=channel_message_id,
                **upload_params
            )
        return message
        
    except FloodWait as e:
        print(f"⏳ Flood wait during forward: {e.value}s")
        await asyncio.sleep(e.value)
        return await forward_from_channel(client, channel_message_id, chat_id, file_name, caption, file_type, progress_callback)
    except Exception as e:
        print(f"❌ Error forwarding from channel: {e}")
        raise

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

# ULTRA FAST FILE PROCESSING WITH TELEGRAM CHANNEL STORAGE
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
        status_msg = await message.reply_text("⚡ **INITIALIZING TELEGRAM CHANNEL STORAGE PROCESS...**")
        
        # Generate unique file hash
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}_{new_name}".encode()).hexdigest()[:16]
        
        # Check if file already exists in channel storage
        existing_message_id = get_file_mapping(file_hash)
        if existing_message_id:
            await status_msg.edit_text("🔄 **File found in channel storage, forwarding...**")
            channel_message_id = existing_message_id
            storage_status = "🔄 FROM EXISTING"
        else:
            # STEP 1: Download file temporarily
            temp_path = f"temp/{file_hash}_{new_name}"
            
            download_progress = UltraFastProgress(file_size, "download")
            last_update = 0
            
            async def download_callback(current, total):
                nonlocal last_update
                metrics = download_progress.update(current)
                current_time = time.time()
                if metrics and (current_time - last_update >= 1.0 or current == total):
                    try:
                        await status_msg.edit_text(
                            f"📥 **DOWNLOADING TO TEMP STORAGE**\n\n{download_progress.get_progress_text(new_name)}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        last_update = current_time
                    except Exception as e:
                        print(f"Progress error: {e}")
            
            await status_msg.edit_text("📥 **DOWNLOADING TO TEMPORARY STORAGE...**")
            download_start = time.time()
            download_path = await ultra_fast_download(client, target_message, temp_path, download_callback)
            download_time = time.time() - download_start
            
            if not download_path or not os.path.exists(download_path):
                await status_msg.edit_text("❌ Download failed! File not found.")
                return
            
            downloaded_size = os.path.getsize(download_path)
            
            # STEP 2: Save to Telegram Channel Storage
            await status_msg.edit_text("💾 **SAVING TO TELEGRAM CHANNEL STORAGE...**")
            
            storage_caption = f"🔗 File Hash: {file_hash}\n👤 User: {user_id}\n⏰ Saved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            storage_start = time.time()
            channel_message_id = await save_to_channel(client, download_path, new_name, storage_caption)
            storage_time = time.time() - storage_start
            
            if not channel_message_id:
                await status_msg.edit_text("❌ Failed to save file to channel storage! Check bot permissions.")
                return
            
            # Save file mapping
            save_file_mapping(file_hash, channel_message_id)
            storage_status = "💾 NEW STORAGE"
            
            await status_msg.edit_text(f"✅ **File saved to channel storage!**\n\n**Channel:** {STORAGE_CHANNEL}\n**Hash:** `{file_hash}`")
        
        # STEP 3: Forward from channel to user
        await status_msg.edit_text("📤 **FORWARDING FROM CHANNEL STORAGE...**")
        
        # Get user caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), f"**{new_name}**\n\n💾 **Stored in Telegram Channel**")
        
        # Determine upload type
        upload_mode = get_upload_mode(user_id)
        if upload_mode == "auto":
            final_upload_type = file_type
        else:
            final_upload_type = upload_mode
        
        upload_progress = UltraFastProgress(file_size, "upload")
        last_upload_update = 0
        
        async def upload_callback(current, total):
            nonlocal last_upload_update
            metrics = upload_progress.update(current)
            current_time = time.time()
            if metrics and (current_time - last_upload_update >= 1.0 or current == total):
                try:
                    await status_msg.edit_text(
                        f"📤 **FORWARDING FROM CHANNEL**\n\n{upload_progress.get_progress_text(new_name)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_upload_update = current_time
                except Exception as e:
                    print(f"Upload progress error: {e}")
        
        upload_start = time.time()
        
        # Forward from channel storage
        try:
            sent_message = await forward_from_channel(
                client, 
                channel_message_id, 
                message.chat.id, 
                new_name, 
                user_caption, 
                final_upload_type, 
                upload_callback
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Error forwarding from channel: {str(e)}")
            return
        
        upload_time = time.time() - upload_start
        total_time = time.time() - start_time
        
        # Performance calculation
        download_speed = file_size / download_time if download_time > 0 else 0
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        
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
            f"📦 **Size:** {format_size(file_size)}\n"
            f"⏱ **Total Time:** {format_duration(total_time)}\n\n"
            f"📥 **Download:** {format_size(download_speed)}/s\n"
            f"📤 **Upload:** {format_size(upload_speed)}/s\n"
            f"🔧 **Mode:** {final_upload_type.upper()}\n"
            f"🖼️ **Thumbnail:** {thumbnail_used}\n"
            f"💾 **Storage:** {storage_status}\n"
            f"🏷️ **Prefix:** {'✅' if user_prefix else '❌'}\n\n"
            f"**Status:** 💾 **TELEGRAM CHANNEL STORAGE ACTIVE**"
        )
        
        # Update stats
        stats = load_json(STATS_DB)
        stats["total_files"] = stats.get("total_files", 0) + 1
        save_json(STATS_DB, stats)
        
        # Update user stats
        users = load_json(USER_DB)
        user_id_str = str(user_id)
        if user_id_str not in users:
            users[user_id_str] = {"files_processed": 0, "joined_at": datetime.now().isoformat()}
        users[user_id_str]["files_processed"] = users[user_id_str].get("files_processed", 0) + 1
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
            "2. Wait for ultra fast processing\n\n"
            f"**Max Size:** {format_size(MAX_FILE_SIZE)}\n"
            f"**Storage:** 💾 **TELEGRAM CHANNEL**\n"
            f"**Channel:** {STORAGE_CHANNEL}"
        )
        return
    
    if not message.reply_to_message.media:
        await message.reply_text("❌ Please reply to a media file (document, video, audio, photo)")
        return
    
    user_processing[user_id] = True
    
    try:
        await ultra_fast_process_file(client, message, message.reply_to_message)
    except Exception as e:
        await message.reply_text(f"❌ Processing error: {str(e)}")
    finally:
        user_processing[user_id] = False

# CHANNEL TEST COMMAND
@app.on_message(filters.command("test_channel"))
async def test_channel_command(client, message: Message):
    """Test channel access and permissions"""
    status_msg = await message.reply_text("🔍 **Testing channel access...**")
    
    try:
        # Test channel access
        channel_access = await verify_channel_access(client)
        if not channel_access:
            await status_msg.edit_text(
                "❌ **Channel Access Failed!**\n\n"
                f"**Channel:** {STORAGE_CHANNEL}\n\n"
                "**Please check:**\n"
                "1. Channel exists and is accessible\n"
                "2. Bot is added as admin\n"
                "3. Bot has permission to send messages\n"
                "4. Channel is not private or restricted"
            )
            return
        
        # Test sending a small message
        test_message = await client.send_message(
            STORAGE_CHANNEL,
            "🤖 **Bot Test Message**\n\nThis is a test to verify channel access."
        )
        
        await status_msg.edit_text(
            "✅ **Channel Access Verified!**\n\n"
            f"**Channel:** {STORAGE_CHANNEL}\n"
            f"**Test Message ID:** {test_message.id}\n"
            "**Status:** Ready to store files! 🎯"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Channel Test Failed:** {str(e)}")

# THUMBNAIL COMMANDS (same as before)
@app.on_message(filters.command("setthumb"))
async def set_thumbnail_command(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text("❌ Reply to a photo with /setthumb to set as thumbnail")
        return
    user_id = message.from_user.id
    try:
        thumb_path = f"thumbnails/{user_id}.jpg"
        await message.reply_to_message.download(thumb_path)
        if set_user_thumbnail(user_id, thumb_path):
            await message.reply_text("✅ Thumbnail set successfully!")
        else:
            await message.reply_text("❌ Failed to save thumbnail")
    except Exception as e:
        await message.reply_text(f"❌ Error setting thumbnail: {str(e)}")

@app.on_message(filters.command(["delthumb", "deletethumb"]))
async def delete_thumbnail_command(client, message: Message):
    user_id = message.from_user.id
    if delete_user_thumbnail(user_id):
        await message.reply_text("✅ Thumbnail deleted successfully!")
    else:
        await message.reply_text("❌ No thumbnail found to delete")

@app.on_message(filters.command("viewthumb"))
async def view_thumbnail_command(client, message: Message):
    user_id = message.from_user.id
    thumbnail_path = get_user_thumbnail(user_id)
    if thumbnail_path and os.path.exists(thumbnail_path):
        await message.reply_photo(thumbnail_path, caption="🖼️ Your current thumbnail")
    else:
        await message.reply_text("❌ No thumbnail set. Use /setthumb to set one.")

# AUTO THUMBNAIL FROM PHOTOS
@app.on_message(filters.photo & filters.private)
async def auto_set_thumbnail(client, message: Message):
    user_id = message.from_user.id
    try:
        thumb_path = f"thumbnails/{user_id}.jpg"
        await message.download(thumb_path)
        if set_user_thumbnail(user_id, thumb_path):
            await message.reply_text("✅ Thumbnail set automatically from your photo!")
        else:
            await message.reply_text("❌ Failed to set thumbnail")
    except Exception as e:
        await message.reply_text(f"❌ Error setting thumbnail: {str(e)}")

# STORAGE STATUS COMMAND
@app.on_message(filters.command("storage"))
async def storage_status_command(client, message: Message):
    mappings = load_json(FILE_MAPPING_DB)
    total_files = len(mappings)
    
    # Test channel access
    channel_access = await verify_channel_access(client)
    channel_status = "✅ Connected" if channel_access else "❌ Disconnected"
    
    await message.reply_text(
        f"💾 **TELEGRAM CHANNEL STORAGE STATUS**\n\n"
        f"**Storage Channel:** {STORAGE_CHANNEL}\n"
        f"**Channel Status:** {channel_status}\n"
        f"**Total Files Stored:** {total_files}\n"
        f"**Max File Size:** {format_size(MAX_FILE_SIZE)}\n\n"
        f"**Test Channel:** `/test_channel`\n"
        f"**Status:** {'✅ **ACTIVE**' if channel_access else '❌ **CHECK CONFIGURATION**'}"
    )

# START COMMAND
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    web_status = "✅ Running" if web_server_started else "❌ Stopped"
    channel_access = await verify_channel_access(client)
    channel_status = "✅ Connected" if channel_access else "❌ Check /storage"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Settings", callback_data="settings")],
        [InlineKeyboardButton("💾 Storage", callback_data="storage_status")],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail_settings")],
        [InlineKeyboardButton("🌐 Status", url=web_server_url)]
    ])
    
    await message.reply_text(
        f"💾 **TELEGRAM CHANNEL STORAGE BOT**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        f"**Storage System:**\n"
        f"• 💾 Channel: {STORAGE_CHANNEL}\n"
        f"• 📊 Status: {channel_status}\n"
        f"• ⚡ Instant file renaming\n"
        f"• 🖼️ Custom thumbnails\n\n"
        f"**How to use:** Reply to any file with `/rename new_filename.ext`\n\n"
        f"**💾 NO LOCAL STORAGE - ALL FILES IN TELEGRAM CHANNEL!**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Other commands and callbacks (same as before)
@app.on_message(filters.command("settings"))
async def settings_command(client, message: Message):
    user_id = message.from_user.id
    prefix = get_user_prefix(user_id)
    upload_mode = get_upload_mode(user_id)
    has_thumbnail = "✅" if get_user_thumbnail(user_id) else "❌"
    channel_access = await verify_channel_access(client)
    channel_status = "✅ Connected" if channel_access else "❌ Disconnected"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Set Prefix", callback_data="set_prefix")],
        [InlineKeyboardButton("📤 Upload Mode", callback_data="upload_mode")],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail_settings")],
        [InlineKeyboardButton("💾 Storage", callback_data="storage_status")],
        [InlineKeyboardButton("🔍 Test Channel", callback_data="test_channel")]
    ])
    
    await message.reply_text(
        f"🔧 **BOT SETTINGS**\n\n"
        f"**Current Settings:**\n"
        f"• **Prefix:** `{prefix if prefix else 'None'}`\n"
        f"• **Upload Mode:** {upload_mode.upper()}\n"
        f"• **Thumbnail:** {has_thumbnail}\n"
        f"• **Storage:** {channel_status}\n\n"
        f"**Commands:**\n"
        f"• `/rename filename.ext` - Rename files\n"
        f"• `/set_prefix text` - Set custom prefix\n"
        f"• `/setthumb` - Set thumbnail\n"
        f"• `/storage` - Storage status\n"
        f"• `/test_channel` - Test channel access\n\n"
        f"**Choose an option:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Callback handlers (same structure as before)
@app.on_callback_query(filters.regex("storage_status"))
async def storage_status_callback(client, callback_query):
    await callback_query.answer()
    await storage_status_command(client, callback_query.message)

@app.on_callback_query(filters.regex("test_channel"))
async def test_channel_callback(client, callback_query):
    await callback_query.answer()
    await test_channel_command(client, callback_query.message)

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
        f"🖼️ **THUMBNAIL SETTINGS**\n\n**Status:** {has_thumbnail}\n\n**How to set:**\n1. Send any photo to this chat\n2. Or use /setthumb command\n\n**Supported for:** Videos, Audio, Documents\n\n**Choose action:**",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Other callback handlers remain the same...
@app.on_callback_query(filters.regex("set_thumbnail"))
async def set_thumbnail_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "🖼️ **SET THUMBNAIL**\n\nTo set a thumbnail:\n\n**Method 1:** Simply send any photo to this chat\n**Method 2:** Reply to a photo with `/setthumb` command\n\nThe thumbnail will be automatically used for your video, audio, and document uploads.",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("view_thumbnail"))
async def view_thumbnail_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    thumbnail_path = get_user_thumbnail(user_id)
    if thumbnail_path and os.path.exists(thumbnail_path):
        await callback_query.message.reply_photo(thumbnail_path, caption="🖼️ Your current thumbnail")
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

@app.on_callback_query(filters.regex("settings"))
async def settings_callback(client, callback_query):
    await callback_query.answer()
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex("set_prefix"))
async def set_prefix_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "🔧 **SET PREFIX**\n\nUse `/set_prefix your_prefix` to set a custom prefix.\n\n**Example:** `/set_prefix MOVIE_`\n\nAll renamed files will have this prefix added automatically.",
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
        f"📤 **UPLOAD MODE**\n\n**Current:** {current_mode.upper()}\n\n**Modes:**\n• 🤖 **Auto:** Smart file type detection\n• 📁 **Document:** Force as document file\n• 🎥 **Video:** Force as video file\n\n**Choose mode:**",
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
            f"✅ **UPLOAD MODE UPDATED**\n\n**New Mode:** {mode.upper()}\n\nAll future uploads will use this mode.\n**Status:** ⚡ **OPTIMIZED FOR SPEED**",
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
        await message.reply_text(f"✅ Prefix set: `{prefix}`\n\n💾 **Now using Telegram Channel Storage!**")
    else:
        await message.reply_text("❌ Failed to set prefix!")

# START BOT WITH CHANNEL VERIFICATION
if __name__ == "__main__":
    print("💾 STARTING TELEGRAM CHANNEL STORAGE BOT...")
    print("🚀 Storage System:")
    print(f"   • Storage Channel: {STORAGE_CHANNEL}")
    print(f"   • Max File Size: {format_size(MAX_FILE_SIZE)}")
    print(f"   • Workers: {MAX_WORKERS}")
    
    # Start web server
    start_web_server()
    
    print(f"🌐 Web Dashboard: {web_server_url}")
    
    # Verify channel access on startup
    async def verify_on_startup():
        async with app:
            channel_access = await verify_channel_access(app)
            if channel_access:
                print("✅ Channel access verified - Bot is ready!")
            else:
                print("❌ Channel access failed - Check configuration!")
                print("💡 Make sure:")
                print("   1. Channel exists: " + STORAGE_CHANNEL)
                print("   2. Bot is admin in the channel")
                print("   3. Bot can send messages")
                print("   4. Use /test_channel command to verify")
    
    # Run verification
    try:
        app.run(verify_on_startup())
    except Exception as e:
        print(f"❌ Startup error: {e}")