import os
import asyncio
import logging
import sys
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType
import aiofiles
import json
import time
from datetime import datetime
from typing import Union

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMIN", "").split() if admin_id.strip()]

# Initialize bot
app = Client(
    "file_rename_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Storage files
THUMBNAIL_DB = "thumbnails.json"
CAPTION_DB = "captions.json"
USER_DB = "users.json"

# Ensure storage directories exist
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# Helper functions for data management
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
            "last_active": datetime.now().isoformat()
        }
        save_json(USER_DB, users)

def update_user_activity(user_id):
    users = load_json(USER_DB)
    if str(user_id) in users:
        users[str(user_id)]["last_active"] = datetime.now().isoformat()
        save_json(USER_DB, users)

# Admin check decorator
def admin_only(func):
    async def wrapper(client, message):
        if message.from_user.id not in ADMINS:
            await message.reply("🚫 **Access Denied!** This command is for admins only.")
            return
        return await func(client, message)
    return wrapper

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    save_user(user_id)
    
    await message.reply_text(
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "I'm a powerful file rename bot with thumbnail and caption management features.\n\n"
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
        "1. Send any file (document, video, audio)\n"
        "2. Reply to that file with `/rename new_filename.ext`\n\n"
        "**Or use caption method:**\n"
        "Send file with caption: `/rename new_filename.ext`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/your_channel")],
            [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/your_profile")]
        ])
    )

# View thumbnail
@app.on_message(filters.command("view_thumb"))
async def view_thumbnail(client, message: Message):
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
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Check if this is meant to be a thumbnail
    if message.caption and "/set_thumb" in message.caption or not message.caption:
        # Download the photo
        thumb_path = f"thumbnails/{user_id}.jpg"
        
        status_msg = await message.reply_text("📥 **Downloading thumbnail...**")
        await message.download(thumb_path)
        
        # Save to database
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        
        await status_msg.edit_text("✅ **Thumbnail set successfully!**")

# Set caption command
@app.on_message(filters.command("set_caption"))
async def set_caption_command(client, message: Message):
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

# View caption
@app.on_message(filters.command("see_caption"))
async def see_caption(client, message: Message):
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
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    captions = load_json(CAPTION_DB)
    
    if str(user_id) in captions:
        del captions[str(user_id)]
        save_json(CAPTION_DB, captions)
        await message.reply_text("✅ **Custom caption deleted successfully!**")
    else:
        await message.reply_text("❌ **No custom caption found to delete!**")

# Rename command (reply to a file)
@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Check if replying to a file
    if not message.reply_to_message:
        await message.reply_text(
            "**Usage:**\n\n"
            "**Method 1:** Reply to a file with `/rename new_filename.ext`\n"
            "**Method 2:** Send file with caption `/rename new_filename.ext`\n\n"
            "**Supported files:** Documents, Videos, Audio, Voice, Animation"
        )
        return
    
    replied_message = message.reply_to_message
    
    # Check if replied message contains a file
    if not replied_message.media:
        await message.reply_text("❌ **Please reply to a file (document, video, audio, etc.)**")
        return
    
    await process_file_rename(client, message, replied_message)

# File processing with caption method
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.voice | filters.animation) &
    filters.private &
    filters.caption
)
async def rename_from_caption(client, message: Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Check if caption contains rename command
    if message.caption and message.caption.startswith("/rename"):
        await process_file_rename(client, message, message)

async def process_file_rename(client, message: Message, target_message: Message):
    user_id = message.from_user.id
    
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
        
        # Download status
        status_msg = await message.reply_text("📥 **Downloading file...**")
        
        # Download file
        file_path = await target_message.download(file_name=f"downloads/{user_id}_{int(time.time())}")
        
        if not file_path:
            await status_msg.edit_text("❌ **Failed to download file!**")
            return
        
        await status_msg.edit_text("🔄 **Processing file...**")
        
        # Get file information
        file_size = os.path.getsize(file_path)
        
        # Prepare caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), "")
        
        if user_caption:
            # Get file attributes
            file_attr = target_message
            duration = getattr(file_attr, 'duration', 0) or getattr(file_attr, 'video', file_attr).duration if hasattr(file_attr, 'video') else 0
            width = getattr(file_attr, 'width', 0) or getattr(file_attr, 'video', file_attr).width if hasattr(file_attr, 'video') else 0
            height = getattr(file_attr, 'height', 0) or getattr(file_attr, 'video', file_attr).height if hasattr(file_attr, 'video') else 0
            
            final_caption = user_caption.format(
                filename=new_name,
                size=format_size(file_size),
                duration=format_duration(duration),
                width=width,
                height=height
            )
        else:
            final_caption = f"**{new_name}**"
        
        # Get thumbnail
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnail_path = thumbnails.get(str(user_id))
        
        # Use original thumbnail if available and no custom thumbnail
        if not thumbnail_path and hasattr(target_message, 'video') and target_message.video.thumbs:
            thumb = target_message.video.thumbs[0]
            thumbnail_path = await client.download_media(thumb.file_id, file_name=f"downloads/thumb_{user_id}.jpg")
        
        await status_msg.edit_text("📤 **Uploading file...**")
        
        # Determine file type and send
        try:
            if target_message.document:
                await target_message.reply_document(
                    document=file_path,
                    file_name=new_name,
                    caption=final_caption,
                    thumb=thumbnail_path,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif target_message.video:
                await target_message.reply_video(
                    video=file_path,
                    file_name=new_name,
                    caption=final_caption,
                    thumb=thumbnail_path,
                    duration=target_message.video.duration,
                    width=target_message.video.width,
                    height=target_message.video.height,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif target_message.audio:
                await target_message.reply_audio(
                    audio=file_path,
                    file_name=new_name,
                    caption=final_caption,
                    thumb=thumbnail_path,
                    duration=target_message.audio.duration,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif target_message.voice:
                await target_message.reply_voice(
                    voice=file_path,
                    caption=final_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif target_message.animation:
                await target_message.reply_animation(
                    animation=file_path,
                    caption=final_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await status_msg.delete()
            
        except Exception as e:
            await status_msg.edit_text(f"❌ **Upload Error:** {str(e)}")
        
        # Clean up downloaded file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
            
    except Exception as e:
        error_msg = await message.reply_text(f"❌ **Error:** {str(e)}")
        await asyncio.sleep(5)
        await error_msg.delete()

# Helper functions
def format_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"

def format_duration(seconds):
    """Convert seconds to MM:SS format"""
    if not seconds:
        return ""
    
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

# Help command
@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text(
        "**🤖 File Rename Bot Help**\n\n"
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
        "**Supported Files:** Documents, Videos, Audio, Voice, GIFs"
    )

# Admin commands
@app.on_message(filters.command("status"))
@admin_only
async def bot_status(client, message: Message):
    users = load_json(USER_DB)
    total_users = len(users)
    
    # Calculate active users (last 7 days)
    week_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    active_users = sum(
        1 for user_data in users.values() 
        if datetime.fromisoformat(user_data["last_active"]).timestamp() > week_ago
    )
    
    await message.reply_text(
        f"🤖 **Bot Status**\n\n"
        f"• **Total Users:** {total_users}\n"
        f"• **Active Users (7 days):** {active_users}\n"
        f"• **Uptime:** {get_uptime()}\n"
        f"• **Server Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

@app.on_message(filters.command("broadcast"))
@admin_only
async def broadcast_message(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("**Usage:** `/broadcast Your message here`")
        return
    
    broadcast_text = " ".join(message.command[1:])
    users = load_json(USER_DB)
    
    status_msg = await message.reply_text(f"📢 **Broadcasting to {len(users)} users...**")
    
    success = 0
    failed = 0
    
    for user_id in users.keys():
        try:
            await client.send_message(
                int(user_id),
                f"📢 **Broadcast Message**\n\n{broadcast_text}"
            )
            success += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except:
            failed += 1
    
    await status_msg.edit_text(
        f"✅ **Broadcast Completed**\n\n"
        f"• ✅ Success: {success}\n"
        f"• ❌ Failed: {failed}\n"
        f"• 📊 Total: {len(users)}"
    )

@app.on_message(filters.command("restart"))
@admin_only
async def restart_bot(client, message: Message):
    await message.reply_text("🔄 **Restarting bot...**")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Uptime tracker
start_time = time.time()

def get_uptime():
    uptime_seconds = int(time.time() - start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    
    return f"{days}d {hours}h {minutes}m {seconds}s"

# Start the bot
if __name__ == "__main__":
    print("🤖 Bot is starting...")
    # Create necessary directories
    os.makedirs("thumbnails", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    app.run()
