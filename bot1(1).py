import os
import logging
import time
import sys
import asyncio
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait, RPCError
from config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = Config.API_ID
API_HASH = Config.API_HASH
BOT_TOKEN = Config.BOT_TOKEN
ADMINS = Config.ADMINS

# --- Bot Initialization ---
app = Client(
    "file_rename_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- In-memory storage ---
user_data: Dict[int, Dict[str, Any]] = {}
user_states: Dict[int, str] = {}  # Track user states: 'awaiting_filename', 'awaiting_caption', etc.

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return user_id in ADMINS

def validate_filename(filename: str) -> bool:
    """Validate filename for security and length."""
    if not filename or len(filename) > 255:
        return False
    
    # Prevent path traversal and invalid characters
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    return not any(char in filename for char in invalid_chars)

def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return os.path.splitext(filename)[1].lower()

async def cleanup_files(*file_paths):
    """Clean up temporary files."""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error cleaning up file {file_path}: {e}")

# --- Progress Callback ---
async def progress_callback(current: int, total: int, message: Message, action: str, start_time: float):
    """Generic progress callback for downloads/uploads."""
    now = time.time()
    diff = now - start_time
    if diff == 0:
        diff = 0.001

    speed = current / diff
    percentage = (current * 100) / total
    elapsed_time = round(diff)
    
    # Calculate ETA
    if current > 0 and speed > 0:
        time_to_completion = round((total - current) / speed)
    else:
        time_to_completion = 0
    
    # Create progress bar
    progress_bar_length = 20
    filled_length = int(progress_bar_length * current // total)
    progress_bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)
    
    progress_str = (
        f"**{action}...**\n\n"
        f"`{progress_bar}`\n"
        f"**Progress:** {percentage:.1f}%\n"
        f"**Size:** {current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB\n"
        f"**Speed:** {speed/1024/1024:.1f} MB/s\n"
        f"**ETA:** {time_to_completion}s"
    )

    try:
        # Update only once per second to avoid FloodWait
        last_update = user_data.get("last_update", 0)
        if now - last_update >= 1:
            await message.edit_text(progress_str)
            user_data["last_update"] = now
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except RPCError:
        pass

# --- Command Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handler for the /start command."""
    user = message.from_user
    welcome_text = (
        f"👋 **Hello, {user.mention}!**\n\n"
        "I am a powerful File Rename Bot with the following features:\n\n"
        "**✨ Features:**\n"
        "• Rename any file (documents, videos, audio)\n"
        "• Set custom thumbnails\n"
        "• Set custom captions\n"
        "• Progress tracking for uploads/downloads\n\n"
        "**📝 How to use:**\n"
        "1. Send me any file you want to rename\n"
        "2. I'll ask for the new file name\n"
        "3. Optional: Send a photo to set as custom thumbnail\n"
        "4. Optional: Use /set_caption to add custom caption\n\n"
        "Use the buttons below for quick actions!"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("🖼️ View Thumb", callback_data="view_thumb")
        ],
        [
            InlineKeyboardButton("📝 View Caption", callback_data="see_caption"),
            InlineKeyboardButton("🗑️ Clear All", callback_data="clear_all")
        ],
        [
            InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/your_developer_username")
        ]
    ])
    
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Handler for /help command."""
    help_text = (
        "**🤖 File Rename Bot - Help**\n\n"
        "**Available Commands:**\n"
        "• `/start` - Start the bot\n"
        "• `/help` - Show this help message\n"
        "• `/view_thumb` - View your saved thumbnail\n"
        "• `/del_thumb` - Delete your saved thumbnail\n"
        "• `/set_caption <caption>` - Set custom caption\n"
        "• `/see_caption` - View your custom caption\n"
        "• `/del_caption` - Delete your custom caption\n\n"
        "**Admin Commands:**\n"
        "• `/restart` - Restart the bot\n"
        "• `/status` - Check bot status\n"
        "• `/broadcast` - Broadcast message to all users\n\n"
        "**Usage:**\n"
        "1. Send any file (document, video, audio)\n"
        "2. Reply with new filename when asked\n"
        "3. That's it! Your file will be renamed and sent back\n\n"
        "**Pro Tips:**\n"
        "• You can set a permanent thumbnail using /set_thumb\n"
        "• Set a default caption using /set_caption\n"
        "• Supported formats: All documents, videos, audio files"
    )
    await message.reply_text(help_text, disable_web_page_preview=True)

@app.on_message(filters.command("view_thumb") & filters.private)
async def view_thumb_command(client: Client, message: Message):
    """Handler for /view_thumb command."""
    user_id = message.from_user.id
    if user_id in user_data and "thumbnail" in user_data[user_id]:
        thumb_file_id = user_data[user_id]["thumbnail"]
        await message.reply_photo(
            photo=thumb_file_id,
            caption="🖼️ **Your current thumbnail**\n\nUse /del_thumb to remove this thumbnail."
        )
    else:
        await message.reply_text("❌ You don't have any thumbnail saved.\n\nSend me a photo to set it as thumbnail.")

@app.on_message(filters.command("del_thumb") & filters.private)
async def delete_thumb_command(client: Client, message: Message):
    """Handler for /del_thumb command."""
    user_id = message.from_user.id
    if user_id in user_data and "thumbnail" in user_data[user_id]:
        del user_data[user_id]["thumbnail"]
        await message.reply_text("✅ Your custom thumbnail has been deleted successfully.")
    else:
        await message.reply_text("❌ You don't have any thumbnail to delete.")

@app.on_message(filters.command("set_caption") & filters.private)
async def set_caption_command(client: Client, message: Message):
    """Handler for /set_caption command."""
    if len(message.command) > 1:
        user_id = message.from_user.id
        caption = message.text.split(" ", 1)[1]
        
        if len(caption) > 1024:
            await message.reply_text("❌ Caption too long! Maximum 1024 characters allowed.")
            return
            
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["caption"] = caption
        await message.reply_text("✅ Your custom caption has been saved successfully!")
    else:
        await message.reply_text(
            "**Usage:** `/set_caption your caption text here`\n\n"
            "**Example:**\n"
            "`/set_caption My Awesome File - Shared via @YourBot`"
        )

@app.on_message(filters.command("see_caption") & filters.private)
async def see_caption_command(client: Client, message: Message):
    """Handler for /see_caption command."""
    user_id = message.from_user.id
    if user_id in user_data and "caption" in user_data[user_id]:
        caption = user_data[user_id]["caption"]
        await message.reply_text(
            f"📝 **Your current custom caption:**\n\n`{caption}`\n\n"
            "Use /del_caption to remove this caption."
        )
    else:
        await message.reply_text("❌ You don't have any custom caption saved.\n\nUse /set_caption to add one.")

@app.on_message(filters.command("del_caption") & filters.private)
async def delete_caption_command(client: Client, message: Message):
    """Handler for /del_caption command."""
    user_id = message.from_user.id
    if user_id in user_data and "caption" in user_data[user_id]:
        del user_data[user_id]["caption"]
        await message.reply_text("✅ Your custom caption has been deleted successfully.")
    else:
        await message.reply_text("❌ You don't have any caption to delete.")

# --- Admin Command Handlers ---

@app.on_message(filters.command("restart") & filters.private)
async def restart_command(client: Client, message: Message):
    """Handler for /restart command (Admin only)."""
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ Access Denied: You are not an admin.")
        return

    restart_msg = await message.reply_text("🔄 Restarting bot...")
    await asyncio.sleep(2)
    
    # For production, consider using a process manager instead
    os.execl(sys.executable, sys.executable, *sys.argv)

@app.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    """Handler for /status command (Admin only)."""
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ Access Denied: You are not an admin.")
        return
    
    total_users = len(user_data)
    total_admins = len(ADMINS)
    
    status_text = (
        "🤖 **Bot Status**\n\n"
        f"• **Total Users:** {total_users}\n"
        f"• **Admins:** {total_admins}\n"
        f"• **Uptime:** {time.ctime()}\n"
        f"• **Bot:** Running ✅"
    )
    
    await message.reply_text(status_text)

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client: Client, message: Message):
    """Handler for /broadcast command (Admin only)."""
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ Access Denied: You are not an admin.")
        return

    if not message.reply_to_message:
        await message.reply_text("❌ Please reply to a message to broadcast it.")
        return

    broadcast_msg = message.reply_to_message
    total_users = len(user_data)
    sent_count = 0
    failed_count = 0
    
    status_msg = await message.reply_text(f"📢 Broadcasting to {total_users} users...\n\nSent: 0 | Failed: 0")

    for user_id in list(user_data.keys()):
        try:
            await broadcast_msg.copy(chat_id=user_id)
            sent_count += 1
            
            # Update status every 10 sends
            if sent_count % 10 == 0:
                await status_msg.edit_text(
                    f"📢 Broadcasting to {total_users} users...\n\n"
                    f"Sent: {sent_count} | Failed: {failed_count}"
                )
            
            # Small delay to avoid flooding
            await asyncio.sleep(0.1)
            
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            failed_count += 1

    await status_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"• **Total Users:** {total_users}\n"
        f"• **Successfully Sent:** {sent_count}\n"
        f"• **Failed:** {failed_count}\n"
        f"• **Success Rate:** {(sent_count/total_users)*100:.1f}%"
    )

# --- File Handling Logic ---

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client: Client, message: Message):
    """Main handler for renaming files."""
    file = message.document or message.video or message.audio
    if not file:
        return

    user_id = message.from_user.id
    
    # Initialize user data if not exists
    if user_id not in user_data:
        user_data[user_id] = {}
    
    # Store file message info
    user_data[user_id].update({
        "file_message_id": message.id,
        "file_type": "video" if message.video else "document" if message.document else "audio",
        "original_file_name": getattr(file, "file_name", "Unknown")
    })
    
    # Set user state
    user_states[user_id] = "awaiting_filename"
    
    # Get current file info
    file_size = file.file_size / (1024 * 1024)  # Convert to MB
    file_name = getattr(file, "file_name", "Unknown")
    
    await message.reply_text(
        f"📁 **File Received!**\n\n"
        f"• **Name:** `{file_name}`\n"
        f"• **Type:** {user_data[user_id]['file_type'].title()}\n"
        f"• **Size:** {file_size:.2f} MB\n\n"
        "**Please send me the new filename** (with extension):\n"
        "Example: `My New File Name.mp4`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
        ])
    )

@app.on_message(filters.private & filters.photo)
async def set_thumbnail(client: Client, message: Message):
    """Handler to set custom thumbnail."""
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["thumbnail"] = message.photo.file_id
    await message.reply_text(
        "✅ **Custom thumbnail saved successfully!**\n\n"
        "This thumbnail will be used for all your future file uploads.\n"
        "Use /view_thumb to see it or /del_thumb to remove it."
    )

@app.on_message(filters.private & filters.text & ~filters.command())
async def get_new_name_and_rename(client: Client, message: Message):
    """Handler for receiving the new file name and performing the rename."""
    user_id = message.from_user.id
    
    # Check if user is in rename state
    if user_id not in user_states or user_states.get(user_id) != "awaiting_filename":
        # Not expecting filename - provide guidance
        await message.reply_text(
            "🤔 **I'm not sure what you want to do.**\n\n"
            "Please send me a file first to rename it, or use /help to see available commands."
        )
        return
    
    new_file_name = message.text.strip()
    
    # Validate filename
    if not validate_filename(new_file_name):
        await message.reply_text(
            "❌ **Invalid filename!**\n\n"
            "Please provide a valid filename:\n"
            "• Must include extension (e.g., .mp4, .pdf, .mp3)\n"
            "• Cannot contain: / \\ : * ? \" < > |\n"
            "• Maximum 255 characters\n\n"
            "**Example:** `My Video File.mp4`"
        )
        return
    
    # Check if user has a file to rename
    if user_id not in user_data or "file_message_id" not in user_data[user_id]:
        await message.reply_text("❌ Error: No file found to rename. Please send a file first.")
        user_states.pop(user_id, None)
        return
    
    file_message_id = user_data[user_id]["file_message_id"]
    
    # Retrieve the original file message
    try:
        original_message = await client.get_messages(user_id, file_message_id)
        if not (original_message.document or original_message.video or original_message.audio):
            await message.reply_text("❌ Error: Original file message not found.")
            user_states.pop(user_id, None)
            return
    except Exception as e:
        await message.reply_text("❌ Error: Could not retrieve the original file.")
        user_states.pop(user_id, None)
        return
    
    # Start the rename process
    status_msg = await message.reply_text("🔄 **Starting file processing...**")
    
    # Prepare file paths
    custom_thumb_id = user_data.get(user_id, {}).get("thumbnail")
    thumb_path = None
    file_path = None
    
    try:
        # Download thumbnail if exists
        if custom_thumb_id:
            try:
                thumb_path = await client.download_media(
                    custom_thumb_id, 
                    file_name=f"thumb_{user_id}_{int(time.time())}.jpg"
                )
            except Exception as e:
                logger.error(f"Error downloading thumbnail: {e}")
                await status_msg.edit_text("⚠️ Could not download thumbnail, proceeding without it...")
        
        # Download the file with progress
        start_time = time.time()
        file_path = await client.download_media(
            message=original_message,
            file_name=f"temp_{user_id}_{new_file_name}",
            progress=progress_callback,
            progress_args=(status_msg, "📥 Downloading", start_time)
        )
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Error: File download failed.")
            return
        
        # Upload the file with new name
        await status_msg.edit_text("📤 **Starting upload...**")
        start_time = time.time()
        
        custom_caption = user_data.get(user_id, {}).get("caption", "")
        file_type = user_data[user_id].get("file_type", "document")
        
        # Send based on file type
        try:
            if file_type == "video":
                await client.send_video(
                    chat_id=user_id,
                    video=file_path,
                    caption=custom_caption,
                    thumb=thumb_path,
                    file_name=new_file_name,
                    progress=progress_callback,
                    progress_args=(status_msg, "📤 Uploading", start_time)
                )
            elif file_type == "document":
                await client.send_document(
                    chat_id=user_id,
                    document=file_path,
                    caption=custom_caption,
                    thumb=thumb_path,
                    file_name=new_file_name,
                    progress=progress_callback,
                    progress_args=(status_msg, "📤 Uploading", start_time)
                )
            elif file_type == "audio":
                await client.send_audio(
                    chat_id=user_id,
                    audio=file_path,
                    caption=custom_caption,
                    thumb=thumb_path,
                    file_name=new_file_name,
                    progress=progress_callback,
                    progress_args=(status_msg, "📤 Uploading", start_time)
                )
        except Exception as e:
            await status_msg.edit_text(f"❌ Error during upload: {str(e)}")
            return
        
        # Success message
        success_text = (
            f"✅ **File Renamed Successfully!**\n\n"
            f"• **Original:** `{user_data[user_id].get('original_file_name', 'Unknown')}`\n"
            f"• **New Name:** `{new_file_name}`\n"
            f"• **Custom Caption:** {'✅' if custom_caption else '❌'}\n"
            f"• **Custom Thumbnail:** {'✅' if thumb_path else '❌'}"
        )
        
        await message.reply_text(success_text)
        await status_msg.delete()
        
    except FloodWait as e:
        await status_msg.edit_text(f"⏳ Too many requests. Waiting {e.value} seconds...")
        await asyncio.sleep(e.value)
        # Don't retry automatically to avoid infinite loops
        await status_msg.edit_text("❌ Operation cancelled due to rate limits. Please try again.")
    except Exception as e:
        logger.error(f"Error during rename process: {e}")
        await status_msg.edit_text(f"❌ **An error occurred:**\n\n`{str(e)}`")
    finally:
        # Cleanup
        await cleanup_files(file_path, thumb_path)
        
        # Reset user state
        user_states.pop(user_id, None)
        if user_id in user_data:
            user_data[user_id].pop("file_message_id", None)
            user_data[user_id].pop("file_type", None)
            user_data[user_id].pop("original_file_name", None)

# --- Callback Query Handlers ---

@app.on_callback_query()
async def handle_callback_query(client, callback_query):
    """Handles all callback queries."""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    try:
        if data == "cancel_rename":
            # Reset user state
            user_states.pop(user_id, None)
            if user_id in user_data:
                user_data[user_id].pop("file_message_id", None)
                user_data[user_id].pop("file_type", None)
                user_data[user_id].pop("original_file_name", None)
            
            await callback_query.message.edit_text("❌ **Rename operation cancelled.**")
            
        elif data == "help":
            help_text = (
                "**🤖 Help Menu**\n\n"
                "**Basic Usage:**\n"
                "1. Send me a file (document/video/audio)\n"
                "2. Provide new filename when asked\n"
                "3. Get your renamed file!\n\n"
                "**Features:**\n"
                "• Rename any file type\n"
                "• Set custom thumbnails\n"
                "• Add custom captions\n"
                "• Progress tracking\n\n"
                "**Commands:** /start, /help, /view_thumb, /del_thumb, /set_caption, /see_caption, /del_caption"
            )
            await callback_query.message.edit_text(help_text, disable_web_page_preview=True)
            
        elif data == "view_thumb":
            if user_id in user_data and "thumbnail" in user_data[user_id]:
                # Send as new message instead of editing
                await callback_query.message.reply_photo(
                    photo=user_data[user_id]["thumbnail"],
                    caption="🖼️ Your current thumbnail"
                )
                await callback_query.answer()
            else:
                await callback_query.answer("You don't have any thumbnail saved!", show_alert=True)
                
        elif data == "see_caption":
            if user_id in user_data and "caption" in user_data[user_id]:
                caption = user_data[user_id]["caption"]
                await callback_query.message.edit_text(f"📝 **Your caption:**\n\n`{caption}`")
            else:
                await callback_query.answer("You don't have any caption saved!", show_alert=True)
                
        elif data == "clear_all":
            user_data.pop(user_id, None)
            user_states.pop(user_id, None)
            await callback_query.message.edit_text("✅ All your settings and data have been cleared!")
        
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await callback_query.answer("An error occurred!", show_alert=True)
    
    await callback_query.answer()

# --- Main Execution ---
if __name__ == "__main__":
    logger.info("🤖 File Rename Bot is starting...")
    try:
        app.run()
        logger.info("Bot stopped gracefully.")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Bot crashed with error: {e}")
        sys.exit(1)