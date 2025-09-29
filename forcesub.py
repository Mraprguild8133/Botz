# (c) @AbirHasan2005

import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config, LOGGER

async def handle_force_subscribe(bot: Client, cmd: (Message | CallbackQuery)):
    if not Config.UPDATES_CHANNEL:
        return 200 # Not configured, so allow access

    try:
        user = await bot.get_chat_member(Config.UPDATES_CHANNEL, cmd.from_user.id)
        if user.status == "kicked":
            await cmd.reply_text(
                "Sorry, you are banned from using me.",
                quote=True,
                disable_web_page_preview=True
            )
            return 400
    except UserNotParticipant:
        try:
            invite_link = await bot.create_chat_invite_link(Config.UPDATES_CHANNEL)
            text = "**Please join my updates channel to use this bot!**\n\nDue to server overload, only channel subscribers can use this bot."
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Join Updates Channel", url=invite_link.invite_link)]
            ])
            if isinstance(cmd, Message):
                await cmd.reply_text(text, reply_markup=markup, quote=True)
            else: # CallbackQuery
                await cmd.message.reply_text(text, reply_markup=markup, quote=True)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as err:
            LOGGER.error(f"Could not handle force sub: {err}")
        return 400
    except Exception as e:
        LOGGER.error(f"Force subscribe check failed: {e}")
        if isinstance(cmd, Message):
            await cmd.reply_text("Something went wrong. Please try again later.", quote=True)
        return 400
    
    return 200
