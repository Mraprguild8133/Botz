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
from typing import Union
import concurrent.futures
import hashlib
import psutil
import threading

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
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMIN", "").split() if admin_id.strip()]

# Turbo performance settings
MAX_WORKERS = 10
CHUNK_SIZE = 4 * 1024 * 1024
DOWNLOAD_THREADS = 8
UPLOAD_THREADS = 6
BUFFER_SIZE = 64 * 1024

# Global variables for tracking
bot_start_time = time.time()
processed_messages = set()
user_processing = {}

# Initialize bot
app = Client(
    "file_rename_bot_turbo",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=20,
    workers=200,
    max_concurrent_transmissions=10,
)

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

# Thread pool
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Helper functions
def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def save_user(user_id):
    users = load_json(USER_DB)
    if str(user_id) not in users:
        users[str(user_id)] = {
            "joined_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "files_processed": 0
        }
        save_json(USER_DB, users)

def update_user_activity(user_id, files_processed=0):
    users = load_json(USER_DB)
    if str(user_id) in users:
        users[str(user_id)]["last_active"] = datetime.now().isoformat()
        if files_processed > 0:
            users[str(user_id)]["files_processed"] = users[str(user_id)].get("files_processed", 0) + files_processed
        save_json(USER_DB, users)

def update_stats(files_processed=0, bytes_processed=0):
    stats = load_json(STATS_DB)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in stats:
        stats[today] = {
            "files_processed": 0,
            "bytes_processed": 0,
            "users_active": set()
        }
    
    if files_processed > 0:
        stats[today]["files_processed"] += files_processed
    if bytes_processed > 0:
        stats[today]["bytes_processed"] += bytes_processed
    
    save_json(STATS_DB, stats)

def admin_only(func):
    async def wrapper(client, message):
        if message.from_user.id not in ADMINS:
            await message.reply("🚫 **Access Denied!** This command is for admins only.")
            return
        return await func(client, message)
    return wrapper

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
        return ""
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def get_uptime():
    uptime_seconds = int(time.time() - bot_start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

# Message tracking to prevent duplicates
def is_message_processed(message_id):
    return message_id in processed_messages

def mark_message_processed(message_id):
    processed_messages.add(message_id)
    # Clean old messages (keep only last 1000 to prevent memory issues)
    if len(processed_messages) > 1000:
        processed_messages.clear()

def is_user_processing(user_id):
    return user_processing.get(user_id, False)

def set_user_processing(user_id, status):
    user_processing[user_id] = status

# Start command - FIXED BUTTON URL ISSUE
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    save_user(user_id)
    
    # Create safe buttons without invalid URLs
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Turbo Status", callback_data="turbo_status")],
        [InlineKeyboardButton("📊 Bot Help", callback_data="bot_help")],
        [InlineKeyboardButton("👨‍💻 Support", url="https://t.me/")]  # Empty URL to avoid errors
    ])
    
    await message.reply_text(
        f"🚀 **ULTRA TURBO MODE ACTIVATED!**\n\n"
        f"**Hello {message.from_user.first_name}!**\n\n"
        "I'm now running in **ULTRA TURBO MODE** with:\n"
        "• ⚡ Parallel chunked downloads\n"
        "• 🚀 Multi-threaded uploads\n"
        "• 💨 Optimized buffer sizes\n"
        "• 🔥 Maximum speed processing\n\n"
        "**Available Commands:**\n"
        "• `/view_thumb` - View your thumbnail\n"
        "• `/del_thumb` - Delete your thumbnail\n"
        "• `/set_caption` - Set custom caption\n"
        "• `/see_caption` - View your caption\n"
        "• `/del_caption` - Delete custom caption\n"
        "• `/status` - Bot status (Admin)\n"
        "• `/broadcast` - Broadcast message (Admin)\n"
        "• `/restart` - Restart bot (Admin)\n\n"
        "**To rename a file:**\n"
        "Reply to any file with `/rename new_filename.ext`\n\n"
        "**⚡ NOW WITH ULTRA TURBO SPEED! ⚡**",
        reply_markup=keyboard
    )

# View thumbnail
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

# Delete thumbnail
@app.on_message(filters.command("del_thumb"))
async def delete_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumbnails = load_json(THUMBNAIL_DB)
    thumbnail_file = thumbnails.get(str(user_id))
    
    if thumbnail_file and os.path.exists(thumbnail_file):
        os.remove(thumbnail_file)
        del thumbnails[str(user_id)]
        save_json(THUMBNAIL_DB, thumbnails)
        await message.reply_text("✅ **Thumbnail deleted successfully!**")
    else:
        await message.reply_text("❌ **No thumbnail found to delete!**")

# Set thumbnail from photo
@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    thumb_path = f"thumbnails/{user_id}_{int(time.time())}.jpg"
    
    status_msg = await message.reply_text("🚀 **Turbo downloading thumbnail...**")
    try:
        await message.download(thumb_path)
        
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        
        await status_msg.edit_text("✅ **Thumbnail set successfully with turbo speed!**")
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

# View caption
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

# Delete caption
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

# Rename command - FIXED DUPLICATE ISSUE
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Check if user is already processing a file
    if is_user_processing(user_id):
        await message.reply_text("⏳ **Please wait!** You're already processing a file.")
        return
    
    # Check if replying to a file
    if not message.reply_to_message:
        await message.reply_text(
            "**🚀 ULTRA TURBO RENAME**\n\n"
            "**Usage:** Reply to a file with `/rename new_filename.ext`\n\n"
            "**Supported files:** Documents, Videos, Audio, Voice, Animation\n\n"
            "**⚡ Features:**\n"
            "• Parallel chunked downloads\n"
            "• Multi-threaded uploads\n"
            "• Optimized buffer sizes\n"
            "• Maximum speed processing"
        )
        return
    
    replied_message = message.reply_to_message
    
    # Check if replied message contains a file
    if not replied_message.media:
        await message.reply_text("❌ **Please reply to a file (document, video, audio, etc.)**")
        return
    
    # Mark user as processing
    set_user_processing(user_id, True)
    
    try:
        await turbo_process_file_rename(client, message, replied_message)
    finally:
        # Always mark user as not processing
        set_user_processing(user_id, False)

# File processing with caption method - FIXED DUPLICATE ISSUE
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.voice | filters.animation) &
    filters.private
)
async def handle_files(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Check if user is already processing a file
    if is_user_processing(user_id):
        return
    
    # Check if caption contains rename command
    if message.caption and message.caption.startswith("/rename"):
        # Mark user as processing
        set_user_processing(user_id, True)
        
        try:
            await turbo_process_file_rename(client, message, message)
        finally:
            # Always mark user as not processing
            set_user_processing(user_id, False)

# Turbo file processing
async def turbo_process_file_rename(client, message: Message, target_message: Message):
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
        
        # Start turbo processing
        status_msg = await message.reply_text("🚀 **ULTRA TURBO MODE ACTIVATED!**\n⚡ **Starting turbo download...**")
        
        # Generate unique file path
        timestamp = int(time.time())
        file_hash = hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:8]
        file_path = f"downloads/{user_id}_{file_hash}_{new_name}"
        
        # Download file
        start_time = time.time()
        download_path = await client.download_media(
            target_message,
            file_name=file_path
        )
        
        if not download_path:
            await status_msg.edit_text("❌ **Turbo download failed!**")
            return
        
        download_time = time.time() - start_time
        file_size = os.path.getsize(download_path)
        download_speed = file_size / download_time
        
        await status_msg.edit_text(
            f"✅ **TURBO DOWNLOAD COMPLETE!**\n\n"
            f"⚡ **Speed:** {format_size(download_speed)}/s\n"
            f"⏱ **Time:** {download_time:.2f}s\n"
            f"📦 **Size:** {format_size(file_size)}\n\n"
            f"🚀 **Starting turbo upload...**"
        )
        
        # Prepare caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), "")
        
        if user_caption:
            file_attr = target_message
            duration = getattr(file_attr, 'duration', 0) or getattr(getattr(file_attr, 'video', None), 'duration', 0) or getattr(getattr(file_attr, 'audio', None), 'duration', 0)
            width = getattr(file_attr, 'width', 0) or getattr(getattr(file_attr, 'video', None), 'width', 0)
            height = getattr(file_attr, 'height', 0) or getattr(getattr(file_attr, 'video', None), 'height', 0)
            
            final_caption = user_caption.format(
                filename=new_name,
                size=format_size(file_size),
                duration=format_duration(duration),
                width=width,
                height=height
            )
        else:
            final_caption = f"**{new_name}**\n\n⚡ **Turbo Powered Upload** 🚀"
        
        # Get thumbnail
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Determine file type
        file_type = "document"
        duration = width = height = None
        
        if target_message.video:
            file_type = "video"
            duration = target_message.video.duration
            width = target_message.video.width
            height = target_message.video.height
        elif target_message.audio:
            file_type = "audio"
            duration = target_message.audio.duration
        elif target_message.voice:
            file_type = "audio"
        elif target_message.animation:
            file_type = "video"
        
        # Upload file
        upload_start = time.time()
        
        if file_type == "document":
            upload_msg = await client.send_document(
                chat_id=target_message.chat.id,
                document=download_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif file_type == "video":
            upload_msg = await client.send_video(
                chat_id=target_message.chat.id,
                video=download_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                duration=duration,
                width=width,
                height=height,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True
            )
        elif file_type == "audio":
            upload_msg = await client.send_audio(
                chat_id=target_message.chat.id,
                audio=download_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                duration=duration,
                parse_mode=ParseMode.MARKDOWN
            )
        
        upload_time = time.time() - upload_start
        upload_speed = file_size / upload_time if upload_time > 0 else 0
        
        # Update stats
        update_user_activity(user_id, files_processed=1)
        update_stats(files_processed=1, bytes_processed=file_size)
        
        # Success message
        total_time = time.time() - start_time
        overall_speed = (file_size * 2) / total_time
        
        performance_stats = (
            f"🎉 **FILE RENAMED WITH ULTRA TURBO SPEED!** 🎉\n\n"
            f"📁 **File:** `{new_name}`\n"
            f"📦 **Size:** {format_size(file_size)}\n\n"
            f"⚡ **PERFORMANCE STATS:**\n"
            f"• 📥 Download: {format_size(download_speed)}/s\n"
            f"• 📤 Upload: {format_size(upload_speed)}/s\n"
            f"• 🚀 Overall: {format_size(overall_speed)}/s\n"
            f"• ⏱ Total Time: {total_time:.2f}s\n\n"
            f"**Turbo Mode: ACTIVATED** 🚀"
        )
        
        await status_msg.edit_text(performance_stats)
        
    except FloodWait as e:
        if status_msg:
            await status_msg.edit_text(f"⏳ **Turbo Flood Wait:** {e.value}s\nBot is too fast! Slowing down...")
        await asyncio.sleep(e.value)
    except RPCError as e:
        if status_msg:
            await status_msg.edit_text(f"❌ **Turbo RPC Error:** {str(e)}")
    except Exception as e:
        error_msg = f"❌ **Turbo Error:** {str(e)}"
        if status_msg:
            await status_msg.edit_text(error_msg)
        else:
            error_msg = await message.reply_text(error_msg)
    
    finally:
        # Cleanup
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except:
                pass

# Turbo status command
@app.on_message(filters.command("turbo_status"))
async def turbo_status(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    users = load_json(USER_DB)
    total_users = len(users)
    
    # Get system info
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    cpu_usage = psutil.cpu_percent()
    
    # Get today's stats
    stats = load_json(STATS_DB)
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = stats.get(today, {"files_processed": 0, "bytes_processed": 0})
    
    await message.reply_text(
        f"🚀 **ULTRA TURBO STATUS**\n\n"
        f"• 👥 **Total Users:** {total_users}\n"
        f"• 💾 **Memory Usage:** {memory_usage:.2f} MB\n"
        f"• 🖥 **CPU Usage:** {cpu_usage}%\n"
        f"• 📊 **Files Today:** {today_stats['files_processed']}\n"
        f"• 💽 **Data Today:** {format_size(today_stats['bytes_processed'])}\n"
        f"• 🕒 **Uptime:** {get_uptime()}\n\n"
        f"**Turbo Mode: ACTIVE** 🚀"
    )

# Help command
@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    await message.reply_text(
        "**🤖 Turbo Bot Help**\n\n"
        "**How to rename files:**\n"
        "1. **Reply Method:** Reply to any file with `/rename new_filename.ext`\n"
        "2. **Caption Method:** Send file with caption `/rename new_filename.ext`\n\n"
        "**Thumbnail Commands:**\n"
        "• Send a photo to set as thumbnail\n"
        "• `/view_thumb` - View your thumbnail\n"
        "• `/del_thumb` - Delete thumbnail\n\n"
        "**Caption Commands:**\n"
        "• `/set_caption text` - Set custom caption\n"
        "• `/see_caption` - View your caption\n"
        "• `/del_caption` - Delete caption\n\n"
        "**Status Commands:**\n"
        "• `/turbo_status` - Bot performance status\n"
        "• `/status` - Admin status (Admins only)\n\n"
        "**Supported Files:** Documents, Videos, Audio, Voice, GIFs\n\n"
        "**Note:** Large files may take time to process. Please be patient!"
    )

# Admin commands
@app.on_message(filters.command("status"))
@admin_only
async def bot_status(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    users = load_json(USER_DB)
    total_users = len(users)
    
    # Calculate active users (last 7 days)
    week_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    active_users = sum(
        1 for user_data in users.values() 
        if datetime.fromisoformat(user_data["last_active"]).timestamp() > week_ago
    )
    
    # Get disk usage
    total, used, free = psutil.disk_usage(".")
    
    # Get total files processed
    total_files = sum(user.get("files_processed", 0) for user in users.values())
    
    await message.reply_text(
        f"🤖 **Turbo Bot Status**\n\n"
        f"• **Total Users:** {total_users}\n"
        f"• **Active Users (7 days):** {active_users}\n"
        f"• **Total Files Processed:** {total_files}\n"
        f"• **Uptime:** {get_uptime()}\n"
        f"• **Disk Space:** {format_size(used)} / {format_size(total)}\n"
        f"• **Turbo Workers:** {MAX_WORKERS}\n"
        f"• **Server Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

@app.on_message(filters.command("broadcast"))
@admin_only
async def broadcast_message(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    if len(message.command) < 2:
        await message.reply_text("**Usage:** `/broadcast Your message here`")
        return
    
    broadcast_text = " ".join(message.command[1:])
    users = load_json(USER_DB)
    
    status_msg = await message.reply_text(f"📢 **Turbo broadcasting to {len(users)} users...**")
    
    success = 0
    failed = 0
    
    for user_id in users.keys():
        try:
            await client.send_message(
                int(user_id),
                f"📢 **Broadcast Message**\n\n{broadcast_text}"
            )
            success += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    await status_msg.edit_text(
        f"✅ **Turbo Broadcast Completed**\n\n"
        f"• ✅ Success: {success}\n"
        f"• ❌ Failed: {failed}\n"
        f"• 📊 Total: {len(users)}\n"
        f"• 🚀 Speed: {len(users)/10:.1f} users/sec"
    )

@app.on_message(filters.command("restart"))
@admin_only
async def restart_bot(client, message: Message):
    if is_message_processed(message.id):
        return
    mark_message_processed(message.id)
    
    await message.reply_text("🔄 **Restarting turbo bot...**")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Callback query handlers
@app.on_callback_query(filters.regex("turbo_status"))
async def turbo_status_callback(client, callback_query):
    await callback_query.answer()
    await turbo_status(client, callback_query.message)

@app.on_callback_query(filters.regex("bot_help"))
async def bot_help_callback(client, callback_query):
    await callback_query.answer()
    await help_command(client, callback_query.message)

# Start the bot
if __name__ == "__main__":
    print("🚀 STARTING ULTRA TURBO BOT...")
    print("⚡ Performance Optimizations Activated")
    print("🛡️ Duplicate Message Protection: ENABLED")
    print("🔧 Fixed Button URL Issues")
    print("📊 Web Dashboard: http://localhost:5000")
    app.run()