import feedparser
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv
import time
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_monitor.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv('Instagram.env')

class InstagramMonitor:
    def __init__(self):
        self.rss_url = os.getenv('INSTAGRAM_RSS_URL')
        self.instagram_username = os.getenv('INSTAGRAM_USERNAME', 'goosetheband')
        self.instagram_password = os.getenv('INSTAGRAM_PASSWORD')
        self.client = None
        self.last_scrape_attempt = 0
        self.scrape_cooldown = 300  # 5 minutes cooldown between scrape attempts
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        init_db()
        
    def _login(self):
        """Login to Instagram using instagrapi"""
        try:
            if not self.instagram_username or not self.instagram_password:
                logging.error("Instagram credentials not configured")
                return False
                
            if self.client is None:
                self.client = Client()
                
            # Try to login
            self.client.login(self.instagram_username, self.instagram_password)
            logging.info("Successfully logged in to Instagram")
            return True
            
        except LoginRequired as e:
            logging.error(f"Login required: {str(e)}")
            return False
        except ClientError as e:
            logging.error(f"Client error during login: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Error during login: {str(e)}")
            return False
            
    def check_direct_scrape(self):
        """Check Instagram using instagrapi"""
        try:
            # Check if we need to wait before trying again
            current_time = time.time()
            if current_time - self.last_scrape_attempt < self.scrape_cooldown:
                logging.info("Waiting for scrape cooldown period...")
                return None
                
            self.last_scrape_attempt = current_time
            logging.info("Attempting Instagram fetch...")
            
            # Ensure we're logged in
            if not self._login():
                logging.error("Failed to login to Instagram")
                return None
            
            # Get user media
            user_id = self.client.user_id_from_username(self.instagram_username)
            medias = self.client.user_medias(user_id, 1)  # Get only the latest post
            
            if not medias:
                logging.warning("No posts found")
                return None
                
            latest_post = medias[0]
            
            post_id = str(latest_post.id)
            if not post_id:
                logging.error("Post ID is missing")
                return None
                
            latest_known_id = get_latest_post_id()
            
            if latest_known_id and post_id == latest_known_id:
                return None
                
            # Create post data
            post_data = {
                'post_id': post_id,
                'date': latest_post.taken_at.isoformat(),
                'caption': latest_post.caption_text if latest_post.caption_text else '',
                'url': f"https://www.instagram.com/p/{latest_post.code}/",
                'is_video': latest_post.media_type == 2,  # 2 = video
                'video_url': latest_post.video_url if latest_post.media_type == 2 else None,
                'thumbnail_url': latest_post.thumbnail_url if latest_post.media_type == 2 else latest_post.photo_url,
                'source': 'api'
            }
            
            save_post(post_data)
            return post_data
            
        except LoginRequired as e:
            logging.error(f"Login required: {str(e)}")
            self.client = None  # Reset client to force re-login
            return None
        except ClientError as e:
            logging.error(f"Client error: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in API fetch: {str(e)}")
            return None
            
    def check_rss_feed(self):
        """Check Instagram RSS feed for new posts"""
        try:
            feed = feedparser.parse(self.rss_url)
            if not feed.entries:
                logging.warning("No entries found in RSS feed")
                return None
                
            latest_entry = feed.entries[0]
            post_id = latest_entry.get('id', '')
            
            if not post_id:
                logging.error("Post ID is missing from RSS entry")
                return None
                
            # Check if this is a new post
            latest_known_id = get_latest_post_id()
            if latest_known_id and post_id == latest_known_id:
                return None
                
            # Create post data from RSS entry
            post_data = {
                'post_id': post_id,
                'date': latest_entry.get('published', datetime.now().isoformat()),
                'caption': latest_entry.get('description', ''),
                'url': latest_entry.get('link', ''),
                'is_video': False,  # RSS doesn't provide this info
                'video_url': None,
                'thumbnail_url': latest_entry.get('media_content', [{}])[0].get('url', ''),
                'source': 'rss'
            }
            
            save_post(post_data)
            return post_data
            
        except Exception as e:
            logging.error(f"Error checking RSS feed: {str(e)}")
            return None
            
    def get_latest_post(self):
        """Get the latest post using API first, then RSS as fallback"""
        # Try API first
        post = self.check_direct_scrape()
        if post:
            return post
            
        # If API fails, try RSS as fallback
        return self.check_rss_feed()
        
    def get_post_history(self, limit=10):
        """Get post history from database"""
        try:
            return get_post_history(limit)
        except Exception as e:
            logging.error(f"Error getting post history: {str(e)}")
            return [] 