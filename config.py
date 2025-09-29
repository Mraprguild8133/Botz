# (c) @AbirHasan2005 - Modified for no-database operation

import os
import time
import logging
from logging.handlers import RotatingFileHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Logger ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler("RenameBot.txt", maxBytes=50000000, backupCount=10),
        logging.StreamHandler()
    ]
)
LOGGER = logging.getLogger(__name__)

# --- Bot Configs ---
class Config(object):
    # --- Get From Environment Variables ---
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    SESSION_NAME = os.environ.get("SESSION_NAME", "Rename-Bot-0")
    UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL", None)

    # --- Text & Buttons ---
    START_TEXT = """
Hi {mention},

I am a Telegram File / Video Renamer Bot with Custom Thumbnail support.

Send me any media file and I will rename it for you.
"""
    START_BUTTONS = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Help", callback_data="help_button"),
            InlineKeyboardButton("About", callback_data="about_button"),
            InlineKeyboardButton("Close", callback_data="close_button")
        ],
        [InlineKeyboardButton("Developer", url="https://t.me/AbirHasan2005")]
    ])

    HELP_TEXT = """
You can rename any media file using me.

- Send me a media file to rename.
- Reply to that file with the new file name.

**Custom Thumbnail:**
- Send a photo to set it as your custom thumbnail.
- `/show_thumbnail` - To see your current thumbnail.
- `/delete_thumbnail` - To delete your current thumbnail.

**Upload Mode:**
- `/settings` - To change your upload mode between 'Video' and 'Document'.

**Note:** All settings are temporary and will reset if the bot restarts.
"""
    HELP_BUTTONS = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Home", callback_data="home_button"),
            InlineKeyboardButton("About", callback_data="about_button"),
            InlineKeyboardButton("Close", callback_data="close_button")
        ]
    ])

    ABOUT_TEXT = """
**Bot Name:** Renamer Bot (No DB Version)
**Developer:** @AbirHasan2005
**Language:** [Python3](https://python.org)
**Framework:** [Pyrogram](https://pyrogram.org)
**Source Code:** [Click Here](https://github.com/MrMKN/Simple-Rename-Bot)
"""
    ABOUT_BUTTONS = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Home", callback_data="home_button"),
            InlineKeyboardButton("Help", callback_data="help_button"),
            InlineKeyboardButton("Close", callback_data="close_button")
        ]
    ])

    SETTINGS_BUTTONS = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Upload as Video", callback_data="upload_as_doc_false"),
            InlineKeyboardButton("Upload as Document", callback_data="upload_as_doc_true")
        ],
        [InlineKeyboardButton("Close", callback_data="close_button")]
    ])

    CAPTION_TEXT = "**New File Name:** `{new_filename}`\n\n**Renamed By:** {user_mention}"

# --- Other ---
BOT_START_TIME = time.time()
DOWNLOAD_DIR = "downloads/"
