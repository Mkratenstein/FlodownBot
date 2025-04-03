import sqlite3
from datetime import datetime
import threading
import logging

# Create a thread-local storage for database connections
local = threading.local()

def get_db_connection():
    """Get a database connection from the pool or create a new one"""
    if not hasattr(local, 'connection'):
        local.connection = sqlite3.connect('instagram_posts.db', check_same_thread=False)
        # Enable foreign keys
        local.connection.execute('PRAGMA foreign_keys = ON')
        # Enable WAL mode for better concurrency
        local.connection.execute('PRAGMA journal_mode = WAL')
        # Set busy timeout to avoid database locked errors
        local.connection.execute('PRAGMA busy_timeout = 5000')
    return local.connection

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create posts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            date TEXT,
            caption TEXT,
            likes INTEGER,
            comments INTEGER,
            url TEXT,
            is_video BOOLEAN,
            video_url TEXT,
            thumbnail_url TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index on date for faster queries
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC)
    ''')
    
    conn.commit()

def get_latest_post_id():
    """Get the ID of the latest post we've seen"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute('SELECT post_id FROM posts ORDER BY date DESC LIMIT 1')
        result = c.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Error getting latest post ID: {str(e)}")
        return None

def save_post(post_data):
    """Save a new post to the database"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute('''
            INSERT OR REPLACE INTO posts 
            (post_id, date, caption, likes, comments, url, is_video, video_url, thumbnail_url, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_data['post_id'],
            post_data['date'],
            post_data['caption'],
            post_data.get('likes', 0),
            post_data.get('comments', 0),
            post_data['url'],
            post_data['is_video'],
            post_data['video_url'],
            post_data['thumbnail_url'],
            post_data.get('source', 'unknown')
        ))
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error saving post: {str(e)}")
        conn.rollback()
        return False

def get_post_history(limit=10):
    """Get the most recent posts from the database"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute('''
            SELECT * FROM posts 
            ORDER BY date DESC 
            LIMIT ?
        ''', (limit,))
        
        posts = c.fetchall()
        return posts
    except Exception as e:
        logging.error(f"Error getting post history: {str(e)}")
        return [] 