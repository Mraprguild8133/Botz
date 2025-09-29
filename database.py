import sqlite3
import asyncio
import aiosqlite
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name="rename_bot.db"):
        self.db_name = db_name
    
    async def create_tables(self):
        """Create necessary tables"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Users table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        files_processed INTEGER DEFAULT 0
                    )
                ''')
                
                # Files table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        original_name TEXT,
                        new_name TEXT,
                        file_size INTEGER,
                        processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                await db.commit()
                logger.info("Database tables created successfully")
                
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
    
    async def add_user(self, user_id, username=None, first_name=None, last_name=None):
        """Add user to database"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error adding user: {e}")
    
    async def add_file_processed(self, user_id, original_name, new_name, file_size):
        """Add file processing record"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Add file record
                await db.execute('''
                    INSERT INTO files (user_id, original_name, new_name, file_size)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, original_name, new_name, file_size))
                
                # Update user's file count
                await db.execute('''
                    UPDATE users SET files_processed = files_processed + 1
                    WHERE user_id = ?
                ''', (user_id,))
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error adding file record: {e}")
    
    async def get_total_users(self):
        """Get total number of users"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0
    
    async def get_total_files(self):
        """Get total number of files processed"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute("SELECT COUNT(*) FROM files") as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total files: {e}")
            return 0
    
    async def get_user_stats(self, user_id):
        """Get user statistics"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute('''
                    SELECT u.files_processed, COUNT(f.id) as total_files
                    FROM users u
                    LEFT JOIN files f ON u.user_id = f.user_id
                    WHERE u.user_id = ?
                    GROUP BY u.user_id
                ''', (user_id,)) as cursor:
                    result = await cursor.fetchone()
                    return result if result else (0, 0)
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return (0, 0)
