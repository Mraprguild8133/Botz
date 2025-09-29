import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait
import time
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
try:
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    ADMIN_STRING = os.environ.get("ADMIN", "")
    ADMINS = [int(admin_id) for admin_id in ADMIN_STRING.split()]
except (ValueError, TypeError) as e:
    logger.error(f"Error reading environment variables: {e}")
    # You might want to exit or use default values if config is critical
    sys.exit("Error: Environment variables are not set correctly.")


# --- Bot Initialization ---
app = Client("file_rename_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- In-memory storage (for simplicity) ---
# For a production bot, consider using a database like SQLite or Redis.
user_data = {}


# --- Helper Functions ---
def is_admin(user_id):
    """Check if a user is an admin."""
    return user_id in ADMINS

# --- Command Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handler for the /start command."""
    user = message.from_user
    welcome_text = (
        f"👋 **Hello, {user.mention}!**\n\n"
        "I am a powerful File Rename Bot. I can also change thumbnails and update captions.\n\n"
        "**How to use me:**\n"
        "1. Send me any file you want to rename.\n"
        "2. I'll ask for the new file name.\n"
        "3. Send a photo to set it as a custom thumbnail.\n\n"
        "Use the commands below to manage your settings."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Developer", url="https://t.me/your_developer_username")],
        [InlineKeyboardButton("Help", callback_data="help")]
    ])
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("view_thumb") & filters.private)
async def view_thumb_command(client, message):
    """Handler for /view_thumb command."""
    user_id = message.from_user.id
    if user_id in user_data and "thumbnail" in user_data[user_id]:
        thumb_file_id = user_data[user_id]["thumbnail"]
        await message.reply_photo(
            photo=thumb_file_id,
            caption="🖼️ This is your current saved thumbnail."
        )
    else:
        await message.reply_text("❌ You don't have any thumbnail saved.")

@app.on_message(filters.command("del_thumb") & filters.private)
async def delete_thumb_command(client, message):
    """Handler for /del_thumb command."""
    user_id = message.from_user.id
    if user_id in user_data and "thumbnail" in user_data[user_id]:
        del user_data[user_id]["thumbnail"]
        await message.reply_text("✅ Your custom thumbnail has been deleted successfully.")
    else:
        await message.reply_text("❌ You don't have any thumbnail to delete.")

@app.on_message(filters.command("set_caption") & filters.private)
async def set_caption_command(client, message):
    """Handler for /set_caption command."""
    if len(message.command) > 1:
        user_id = message.from_user.id
        caption = message.text.split(" ", 1)[1]
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["caption"] = caption
        await message.reply_text("✅ Your custom caption has been saved successfully.")
    else:
        await message.reply_text("Please provide a caption after the command.\nExample: `/set_caption My Awesome File`")

@app.on_message(filters.command("see_caption") & filters.private)
async def see_caption_command(client, message):
    """Handler for /see_caption command."""
    user_id = message.from_user.id
    if user_id in user_data and "caption" in user_data[user_id]:
        caption = user_data[user_id]["caption"]
        await message.reply_text(f"📝 **Your current custom caption is:**\n\n`{caption}`")
    else:
        await message.reply_text("❌ You don't have any custom caption saved.")

@app.on_message(filters.command("del_caption") & filters.private)
async def delete_caption_command(client, message):
    """Handler for /del_caption command."""
    user_id = message.from_user.id
    if user_id in user_data and "caption" in user_data[user_id]:
        del user_data[user_id]["caption"]
        await message.reply_text("✅ Your custom caption has been deleted successfully.")
    else:
        await message.reply_text("❌ You don't have any caption to delete.")


# --- Admin Command Handlers ---

@app.on_message(filters.command("restart") & filters.private)
async def restart_command(client, message):
    """Handler for /restart command (Admin only)."""
    if not is_admin(message.from_user.id):
        return await message.reply_text("ACCESS DENIED: You are not an admin.")

    msg = await message.reply_text("🔄 Restarting bot...")
    # This is a simple way to restart. For production, consider using a process manager.
    os.execl(sys.executable, sys.executable, *sys.argv)

@app.on_message(filters.command("status") & filters.private)
async def status_command(client, message):
    """Handler for /status command (Admin only)."""
    if not is_admin(message.from_user.id):
        return await message.reply_text("ACCESS DENIED: You are not an admin.")
    
    # A more advanced status would track more metrics.
    total_users = len(user_data) # Simple user count based on in-memory data
    await message.reply_text(f"**Bot Status**\n\n- Total Users (current session): {total_users}")

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message):
    """Handler for /broadcast command (Admin only)."""
    if not is_admin(message.from_user.id):
        return await message.reply_text("ACCESS DENIED: You are not an admin.")

    if message.reply_to_message:
        # This is a simple broadcast. A more robust solution would handle rate limits and errors.
        broadcast_msg = message.reply_to_message
        total_users = len(user_data)
        sent_count = 0
        failed_count = 0
        
        status_msg = await message.reply_text(f"Broadcasting to {total_users} users...")

        for user_id in list(user_data.keys()):
            try:
                await broadcast_msg.copy(chat_id=user_id)
                sent_count += 1
                time.sleep(0.1) # Avoid hitting API limits too quickly
            except FloodWait as e:
                time.sleep(e.x)
            except Exception:
                failed_count += 1
        
        await status_msg.edit_text(f"**Broadcast Complete**\n\n- Sent: {sent_count}\n- Failed: {failed_count}")
    else:
        await message.reply_text("Reply to a message to broadcast it to all users.")


# --- File Handling Logic ---

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client, message):
    """Main handler for renaming files."""
    file = message.document or message.video or message.audio
    if not file:
        return

    # Store the file message ID for later use
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["file_message_id"] = message.id

    await message.reply_text(
        "**File received!**\n\n"
        "Now, please send me the new name for this file (including the extension, e.g., `MyVideo.mp4`).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_rename")]])
    )

@app.on_message(filters.private & filters.photo)
async def set_thumbnail(client, message):
    """Handler to set custom thumbnail."""
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["thumbnail"] = message.photo.file_id
    await message.reply_text("✅ Custom thumbnail has been saved successfully!")

@app.on_message(filters.private & filters.text & ~filters.command())
async def get_new_name_and_rename(client, message):
    """Handler for receiving the new file name and performing the rename."""
    user_id = message.from_user.id
    if user_id not in user_data or "file_message_id" not in user_data[user_id]:
        return

    new_file_name = message.text
    file_message_id = user_data[user_id]["file_message_id"]
    
    # Retrieve the original file message
    original_message = await client.get_messages(user_id, file_message_id)
    if not (original_message.document or original_message.video or original_message.audio):
        return await message.reply_text("Error: Could not find the original file.")

    status_msg = await message.reply_text("🚀 Starting download...")

    # --- Prepare for upload ---
    custom_caption = user_data.get(user_id, {}).get("caption")
    custom_thumb_id = user_data.get(user_id, {}).get("thumbnail")
    thumb_path = None
    if custom_thumb_id:
        thumb_path = await client.download_media(custom_thumb_id, file_name=f"thumb_{user_id}.jpg")

    file_to_rename = original_message.document or original_message.video or original_message.audio
    
    # --- Download and Upload with Progress ---
    try:
        start_time = time.time()
        
        # Download
        file_path = await client.download_media(
            message=original_message,
            file_name=new_file_name,
            progress=progress_callback,
            progress_args=(status_msg, "Downloading", start_time)
        )
        
        # Upload
        await status_msg.edit_text("⬆️ Uploading...")
        start_time = time.time()
        
        if original_message.video:
            await client.send_video(
                chat_id=user_id,
                video=file_path,
                caption=custom_caption,
                thumb=thumb_path,
                file_name=new_file_name,
                progress=progress_callback,
                progress_args=(status_msg, "Uploading", start_time)
            )
        elif original_message.document:
            await client.send_document(
                chat_id=user_id,
                document=file_path,
                caption=custom_caption,
                thumb=thumb_path,
                file_name=new_file_name,
                progress=progress_callback,
                progress_args=(status_msg, "Uploading", start_time)
            )
        elif original_message.audio:
            await client.send_audio(
                chat_id=user_id,
                audio=file_path,
                caption=custom_caption,
                thumb=thumb_path,
                file_name=new_file_name,
                progress=progress_callback,
                progress_args=(status_msg, "Uploading", start_time)
            )

        await status_msg.delete()
        await message.reply_text("✅ File renamed and sent successfully!")

    except Exception as e:
        logger.error(f"Error during rename process: {e}")
        await status_msg.edit_text(f"An error occurred: {e}")
    finally:
        # --- Cleanup ---
        if os.path.exists(file_path):
            os.remove(file_path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # Reset user state
        if user_id in user_data and "file_message_id" in user_data[user_id]:
            del user_data[user_id]["file_message_id"]

async def progress_callback(current, total, message, action, start_time):
    """Generic progress callback for downloads/uploads."""
    now = time.time()
    diff = now - start_time
    if diff == 0:
        diff = 0.001

    speed = current / diff
    percentage = current * 100 / total
    elapsed_time = round(diff)
    time_to_completion = round((total - current) / speed)
    
    progress_str = (
        f"**{action}...**\n"
        f"[{'█' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}]\n"
        f"Percentage: {percentage:.2f}%\n"
        f"Completed: {current/1024/1024:.2f} MB / {total/1024/1024:.2f} MB\n"
        f"Speed: {speed/1024/1024:.2f} MB/s\n"
        f"ETA: {time_to_completion}s"
    )

    try:
        # Edit message only once per second to avoid FloodWait
        if "last_update" not in user_data or (now - user_data["last_update"] > 1):
            await message.edit_text(progress_str)
            user_data["last_update"] = now
    except FloodWait as e:
        time.sleep(e.x)
    except Exception:
        pass


# --- Callback Query Handlers ---

@app.on_callback_query()
async def handle_callback_query(client, callback_query):
    """Handles all callback queries."""
    data = callback_query.data
    if data == "cancel_rename":
        user_id = callback_query.from_user.id
        if user_id in user_data and "file_message_id" in user_data[user_id]:
            del user_data[user_id]["file_message_id"]
        await callback_query.message.edit_text("❌ Rename operation has been cancelled.")
    elif data == "help":
        help_text = (
            "**Help Menu**\n\n"
            "This bot can rename files, change their thumbnail and caption.\n\n"
            "**Available Commands:**\n"
            "/start - Check if I'm alive.\n"
            "/view_thumb - See your saved thumbnail.\n"
            "/del_thumb - Delete your saved thumbnail.\n"
            "/set_caption `<caption>` - Set a custom caption.\n"
            "/see_caption - View your custom caption.\n"
            "/del_caption - Delete your custom caption.\n\n"
            "**Admin Commands:**\n"
            "/restart - Restart the bot.\n"
            "/status - Check bot status.\n"
            "/broadcast - Reply to a message to broadcast it."
        )
        await callback_query.message.edit_text(help_text, disable_web_page_preview=True)
    
    await callback_query.answer()


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Bot is starting...")
    app.run()
    logger.info("Bot has stopped.")
