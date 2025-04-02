import sqlite3
from datetime import datetime

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('instagram_posts.db')
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
    
    conn.commit()
    conn.close()

def get_latest_post_id():
    """Get the ID of the latest post we've seen"""
    conn = sqlite3.connect('instagram_posts.db')
    c = conn.cursor()
    
    c.execute('SELECT post_id FROM posts ORDER BY date DESC LIMIT 1')
    result = c.fetchone()
    
    conn.close()
    return result[0] if result else None

def save_post(post_data):
    """Save a new post to the database"""
    conn = sqlite3.connect('instagram_posts.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT OR REPLACE INTO posts 
        (post_id, date, caption, likes, comments, url, is_video, video_url, thumbnail_url, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        post_data['post_id'],
        post_data['date'],
        post_data['caption'],
        post_data['likes'],
        post_data['comments'],
        post_data['url'],
        post_data['is_video'],
        post_data['video_url'],
        post_data['thumbnail_url'],
        post_data.get('source', 'unknown')
    ))
    
    conn.commit()
    conn.close()

def get_post_history(limit=10):
    """Get the most recent posts from the database"""
    conn = sqlite3.connect('instagram_posts.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM posts 
        ORDER BY date DESC 
        LIMIT ?
    ''', (limit,))
    
    posts = c.fetchall()
    conn.close()
    return posts 