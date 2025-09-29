# (c) @AbirHasan2005 - Modified for no-database operation

import os
import time
import psutil
import shutil
import string
import random
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from helper_func import (
    get_media_from_message,
    get_time,
    get_readable_bytes,
    get_readable_time,
    take_screen_shot
)
from config import (
    Config,
    LOGGER,
    DOWNLOAD_DIR,
    BOT_START_TIME
)
from forcesub import handle_force_subscribe
from display_progress import progress_for_pyrogram, TimeFormatter

# In-memory storage for user settings
user_settings = {}
# Structure: {user_id: {"upload_as_doc": False, "thumbnail": "file_id"}}

RenameBot = Client(
    session_name=Config.SESSION_NAME,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)


@RenameBot.on_message(filters.command("start") & filters.private & ~filters.edited)
async def start_command_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    await update.reply_text(
        text=Config.START_TEXT.format(mention=update.from_user.mention),
        reply_markup=Config.START_BUTTONS,
        disable_web_page_preview=True
    )


@RenameBot.on_message(filters.command("help") & filters.private & ~filters.edited)
async def help_command_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    await update.reply_text(
        text=Config.HELP_TEXT,
        reply_markup=Config.HELP_BUTTONS,
        disable_web_page_preview=True
    )


@RenameBot.on_message(filters.command("about") & filters.private & ~filters.edited)
async def about_command_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    await update.reply_text(
        text=Config.ABOUT_TEXT,
        reply_markup=Config.ABOUT_BUTTONS,
        disable_web_page_preview=True
    )


@RenameBot.on_message(filters.command("status") & filters.private & ~filters.edited)
async def status_command_handler(bot: Client, update: Message):
    uptime = TimeFormatter((time.time() - BOT_START_TIME))
    free = f"{get_readable_bytes(psutil.disk_usage('/').free)}"
    await update.reply_text(
        text=f"**Bot Status:**\n\n"
             f"**Uptime:** `{uptime}`\n"
             f"**Free Disk Space:** `{free}`"
    )


@RenameBot.on_message((filters.video | filters.document) & filters.private & ~filters.edited)
async def media_receive_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    await update.reply_text(
        text="Send the new file name for this file without the extension.",
        reply_to_message_id=update.message_id,
        reply_markup=filters.ForceReply(True)
    )


@RenameBot.on_message(filters.text & filters.private & filters.reply & ~filters.edited)
async def rename_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return

    replied_message = update.reply_to_message
    if not replied_message or not replied_message.reply_to_message:
        return

    original_message = replied_message.reply_to_message
    media = get_media_from_message(original_message)
    if not media:
        await update.reply_text("You did not reply to a valid media file.", quote=True)
        return

    new_file_name = update.text
    if len(new_file_name) > 200:
        await update.reply_text("Sorry! The new file name is too long.", quote=True)
        return

    editable = await update.reply_text("Processing...", quote=True)
    file_path = os.path.join(DOWNLOAD_DIR, str(update.from_user.id), str(time.time()))
    os.makedirs(file_path, exist_ok=True)

    try:
        # Downloading the file
        download_start_time = time.time()
        c_file_name = await bot.download_media(
            message=original_message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading file...", editable, download_start_time)
        )
        if c_file_name is None:
            await editable.edit("Failed to download file!")
            shutil.rmtree(file_path, ignore_errors=True)
            return

        # Renaming the file
        base, extension = os.path.splitext(c_file_name)
        new_file_path = os.path.join(file_path, new_file_name + extension)
        os.rename(c_file_name, new_file_path)

        # Preparing for upload
        upload_start_time = time.time()
        user_id = update.from_user.id
        upload_as_doc = user_settings.get(user_id, {}).get("upload_as_doc", False)
        custom_thumb_file_id = user_settings.get(user_id, {}).get("thumbnail")
        thumb_path = None

        if custom_thumb_file_id:
            try:
                thumb_path = await bot.download_media(custom_thumb_file_id, file_name=os.path.join(file_path, "thumb.jpg"))
            except Exception as e:
                LOGGER.warning(f"Could not download custom thumbnail: {e}")
                thumb_path = None

        caption = Config.CAPTION_TEXT.format(
            new_filename=os.path.basename(new_file_path),
            user_mention=update.from_user.mention
        )

        # Uploading logic
        if not upload_as_doc and media.video:
            if not thumb_path:
                try:
                    thumb_path = await take_screen_shot(new_file_path, file_path, random.randint(0, int(media.duration) - 1))
                except Exception as e:
                    LOGGER.warning(f"Could not take screenshot: {e}")
            await bot.send_video(
                chat_id=update.chat.id,
                video=new_file_path,
                thumb=thumb_path,
                caption=caption,
                reply_to_message_id=original_message.message_id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading file...", editable, upload_start_time)
            )
        else:
            await bot.send_document(
                chat_id=update.chat.id,
                document=new_file_path,
                thumb=thumb_path,
                caption=caption,
                reply_to_message_id=original_message.message_id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading file...", editable, upload_start_time)
            )

        await editable.delete()

    except Exception as err:
        await editable.edit(f"An error occurred: `{err}`\n\nPlease contact support.")
        LOGGER.error(f"Error during rename process for user {update.from_user.id}: {err}", exc_info=True)
    finally:
        shutil.rmtree(file_path, ignore_errors=True)


@RenameBot.on_message(filters.command("settings") & filters.private & ~filters.edited)
async def settings_command_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    
    upload_as_doc = user_settings.get(update.from_user.id, {}).get("upload_as_doc", False)
    text = "Currently, you are uploading files as **Video**." if not upload_as_doc else "Currently, you are uploading files as **Document**."
    text += "\n\n**Note:** These settings are temporary and will be reset if the bot restarts."
    await update.reply_text(
        text=text,
        reply_markup=Config.SETTINGS_BUTTONS
    )


@RenameBot.on_message(filters.photo & filters.private & ~filters.edited)
async def set_thumbnail_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return

    user_id = update.from_user.id
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["thumbnail"] = update.photo.file_id
    await update.reply_text("Custom thumbnail saved successfully!")


@RenameBot.on_message(filters.command("show_thumbnail") & filters.private & ~filters.edited)
async def show_thumbnail_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return

    thumbnail_id = user_settings.get(update.from_user.id, {}).get("thumbnail")
    if thumbnail_id:
        await bot.send_photo(
            chat_id=update.chat.id,
            photo=thumbnail_id,
            caption="This is your current custom thumbnail."
        )
    else:
        await update.reply_text("You have not set a custom thumbnail.")


@RenameBot.on_message(filters.command("delete_thumbnail") & filters.private & ~filters.edited)
async def delete_thumbnail_handler(bot: Client, update: Message):
    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    
    user_id = update.from_user.id
    if user_id in user_settings and "thumbnail" in user_settings[user_id]:
        user_settings[user_id]["thumbnail"] = None
        await update.reply_text("Custom thumbnail deleted successfully!")
    else:
        await update.reply_text("You haven't set a custom thumbnail to delete.")


@RenameBot.on_callback_query()
async def callback_query_handler(bot: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    
    if data == "close_button":
        await query.message.delete()
        return

    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, query)
        if fsub == 400:
            await query.answer("Please join the updates channel first.", show_alert=True)
            return

    if user_id not in user_settings:
        user_settings[user_id] = {}

    if data == "show_settings":
        upload_as_doc = user_settings.get(user_id, {}).get("upload_as_doc", False)
        text = "Currently, you are uploading files as **Video**." if not upload_as_doc else "Currently, you are uploading files as **Document**."
        text += "\n\n**Note:** These settings are temporary and will be reset if the bot restarts."
        await query.message.edit_text(text=text, reply_markup=Config.SETTINGS_BUTTONS)

    elif data == "upload_as_doc_false":
        user_settings[user_id]["upload_as_doc"] = False
        await query.message.edit_text("Upload mode changed to **Video**.", reply_markup=Config.SETTINGS_BUTTONS)

    elif data == "upload_as_doc_true":
        user_settings[user_id]["upload_as_doc"] = True
        await query.message.edit_text("Upload mode changed to **Document**.", reply_markup=Config.SETTINGS_BUTTONS)

    elif data.startswith("home") or data.startswith("help") or data.startswith("about"):
        if data == "home_button":
            text, markup = Config.START_TEXT.format(mention=query.from_user.mention), Config.START_BUTTONS
        elif data == "help_button":
            text, markup = Config.HELP_TEXT, Config.HELP_BUTTONS
        elif data == "about_button":
            text, markup = Config.ABOUT_TEXT, Config.ABOUT_BUTTONS
        await query.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)


if __name__ == "__main__":
    LOGGER.info("Bot is starting...")
    RenameBot.run()
