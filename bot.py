import os
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import aiofiles
import json
import time
from datetime import datetime

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

# Ensure storage files exist
for file in [THUMBNAIL_DB, CAPTION_DB, USER_DB]:
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump({}, f)

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
        "• `/del_caption` - Delete your caption\n"
        "• `/status` - Bot status (Admin)\n"
        "• `/broadcast` - Broadcast message (Admin)\n"
        "• `/restart` - Restart bot (Admin)\n\n"
        "**Just send me any file to rename it!** 🚀",
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
        await message.reply_text("❌ **No thumbnail found!**\nSend an image with `/set_thumb` to set one.")

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

# Set thumbnail
@app.on_message(filters.photo & filters.private)
async def set_thumbnail(client, message: Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    if message.caption and "/set_thumb" in message.caption or not message.caption:
        # Download the photo
        thumb_path = f"thumbnails/{user_id}.jpg"
        os.makedirs("thumbnails", exist_ok=True)
        
        await message.download(thumb_path)
        
        # Save to database
        thumbnails = load_json(THUMBNAIL_DB)
        thumbnails[str(user_id)] = thumb_path
        save_json(THUMBNAIL_DB, thumbnails)
        
        await message.reply_text("✅ **Thumbnail set successfully!**")

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

# File processing handler
@app.on_message(filters.document | filters.video | filters.audio | filters.voice | filters.animation)
async def rename_file(client, message: Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    # Ask for new file name if not in caption
    if not message.caption or not message.caption.startswith("/rename"):
        return
    
    try:
        # Extract new file name from caption
        parts = message.caption.split(" ", 1)
        if len(parts) < 2:
            await message.reply_text("**Usage:** Send file with caption: `/rename NewFileName.ext`")
            return
        
        new_name = parts[1].strip()
        
        # Download status
        status_msg = await message.reply_text("📥 **Downloading file...**")
        
        # Download file
        file_path = await message.download()
        
        await status_msg.edit_text("🔄 **Processing file...**")
        
        # Get file information
        file_size = os.path.getsize(file_path)
        
        # Prepare caption
        captions = load_json(CAPTION_DB)
        user_caption = captions.get(str(user_id), "")
        
        if user_caption:
            # Replace variables in caption
            duration = getattr(message, 'duration', 0)
            width = getattr(message, 'width', 0)
            height = getattr(message, 'height', 0)
            
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
        
        await status_msg.edit_text("📤 **Uploading file...**")
        
        # Determine file type and send
        if message.document:
            await message.reply_document(
                document=file_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif message.video:
            await message.reply_video(
                video=file_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        elif message.audio:
            await message.reply_audio(
                audio=file_path,
                file_name=new_name,
                caption=final_caption,
                thumb=thumbnail_path,
                parse_mode=ParseMode.MARKDOWN
            )
        
        await status_msg.delete()
        
        # Clean up downloaded file
        try:
            os.remove(file_path)
        except:
            pass
            
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

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
    app.run()
