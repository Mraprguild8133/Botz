import os
import shutil
import asyncio
from datetime import datetime, timedelta

def get_file_size(file_path):
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except:
        return 0

def get_human_size(size_bytes):
    """Convert bytes to human readable format"""
    if not size_bytes:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"

async def clean_downloads():
    """Clean downloads directory"""
    downloads_dir = "downloads"
    if not os.path.exists(downloads_dir):
        return
    
    try:
        # Remove files older than 1 hour
        current_time = datetime.now()
        for filename in os.listdir(downloads_dir):
            file_path = os.path.join(downloads_dir, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if current_time - file_time > timedelta(hours=1):
                    try:
                        os.remove(file_path)
                    except:
                        pass
    except Exception as e:
        print(f"Error cleaning downloads: {e}")

def is_supported_format(filename):
    """Check if file format is supported"""
    _, ext = os.path.splitext(filename.lower())
    return ext in [
        '.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
        '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'
                                                   ]
