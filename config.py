import os
import sys
import logging

# Set up logging for config validation
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    """
    Configuration class for the bot.
    Reads environment variables and performs basic validation.
    """
    try:
        API_ID = int(os.environ.get("API_ID"))
        API_HASH = os.environ.get("API_HASH")
        BOT_TOKEN = os.environ.get("BOT_TOKEN")
        ADMIN_STRING = os.environ.get("ADMIN", "6300568870")
        ADMINS = [int(admin_id) for admin_id in ADMIN_STRING.split()] if ADMIN_STRING else []
    except (ValueError, TypeError, AttributeError) as e:
        logger.error(f"One or more environment variables are not set correctly: {e}")
        sys.exit("Error: Ensure API_ID, API_HASH, and BOT_TOKEN are correctly set.")
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading configuration: {e}")
        sys.exit("Error: Could not read configuration.")
