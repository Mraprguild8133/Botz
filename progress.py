# (c) @AbirHasan2005
# This is Telegram Progress Bar for Pyrogram.
# Source: https://github.com/rojserbest/YK-SUB-BOT/blob/main/yakub/utilities/progress.py

import math
import time
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def progress_for_pyrogram(
    current,
    total,
    ud_type,
    message,
    start
):
    now = time.time()
    diff = now - start
    if round(diff % 10.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000 if speed > 0 else 0
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time_str = TimeFormatter(milliseconds=elapsed_time)
        estimated_total_time_str = TimeFormatter(milliseconds=estimated_total_time)

        progress = "[{0}{1}] {2}%\n".format(
            ''.join(["█" for _ in range(math.floor(percentage / 5))]),
            ''.join(["░" for _ in range(20 - math.floor(percentage / 5))]),
            round(percentage, 2)
        )

        tmp = progress + "{0} of {1}\nSpeed: {2}/s\nETA: {3}\n".format(
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),
            estimated_total_time_str if estimated_total_time_str else "0 s"
        )
        try:
            await message.edit(
                text=f"{ud_type}\n{tmp}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Cancel Process", callback_data="cancel_process")]])
            )
        except MessageNotModified:
            pass
        except Exception:
            pass

def humanbytes(size):
    if not size:
        return "0B"
    power = 2**10
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}B"

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((f"{days}d, ") if days else "") + \
          ((f"{hours}h, ") if hours else "") + \
          ((f"{minutes}m, ") if minutes else "") + \
          ((f"{seconds}s, ") if seconds else "") + \
          ((f"{milliseconds}ms, ") if milliseconds else "")
    return tmp[:-2] if tmp else "0s"
