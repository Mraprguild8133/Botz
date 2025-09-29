import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
API_ID = int(os.getenv("API_ID", "1234567"))
API_HASH = os.getenv("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# Bot settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
SUPPORTED_FORMATS = [
    # Documents
    ".pdf", ".txt", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
    # Videos
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    ".3gp", ".m4v", ".mpeg", ".mpg",
    # Audio
    ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"
]

# Database settings
DB_NAME = "rename_bot.db"

# Admin ID (replace with your Telegram user ID)
ADMIN_ID = 123456789  # Replace with your actual user ID
