# (c) @AbirHasan2005

import os
import time
import math
import asyncio
from pyrogram.types import Message
from config import DOWNLOAD_DIR, LOGGER

def get_media_from_message(message: Message):
    media_ops = (
        (message.video, "video"),
        (message.document, "document"),
        (message.audio, "audio")
    )
    for media, _ in media_ops:
        if media:
            return media
    return None

def get_time(seconds: float) -> str:
    seconds = int(seconds)
    if seconds == 0:
        return "0s"
    time_str = ""
    if seconds >= 86400:
        time_str += f"{seconds // 86400}d "
        seconds %= 86400
    if seconds >= 3600:
        time_str += f"{seconds // 3600}h "
        seconds %= 3600
    if seconds >= 60:
        time_str += f"{seconds // 60}m "
        seconds %= 60
    if seconds > 0:
        time_str += f"{seconds}s"
    return time_str.strip()

def get_readable_bytes(size, precision=2):
    if size is None or size <= 0:
        return "0B"
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    power = int(math.log(size, 1024))
    return f"{round(size / (1024 ** power), precision)}{suffixes[power]}"

def get_readable_time():
    return time.strftime("%Hh %Mm %Ss")

async def take_screen_shot(video_file, output_directory, ttl):
    out_put_file_name = os.path.join(output_directory, f"{time.time()}.jpg")
    file_gen_cmd = f"ffmpeg -ss {ttl} -i \"{video_file}\" -vframes 1 \"{out_put_file_name}\""
    process = await asyncio.create_subprocess_shell(
        file_gen_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    if e_response:
        LOGGER.warning(f"ffmpeg stderr for screenshot: {e_response}")
    if os.path.lexists(out_put_file_name):
        return out_put_file_name
    return None
