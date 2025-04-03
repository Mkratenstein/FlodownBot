import feedparser
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv
import time
import instaloader
from instaloader.exceptions import ConnectionException, BadCredentialsException, LoginRequiredException

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
        self.loader = None
        self.last_scrape_attempt = 0
        self.scrape_cooldown = 300  # 5 minutes cooldown between scrape attempts
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        self.use_api = False  # Default to not using API
        init_db()
        
        # Check if we should try using the API
        if self.instagram_username and self.instagram_password:
            self.use_api = True
            logging.info("Instagram credentials found, will attempt API access")
        else:
            logging.info("No Instagram credentials found, will use RSS feed only")
        
    def _login(self):
        """Login to Instagram using instaloader"""
        try:
            if not self.instagram_username or not self.instagram_password:
                logging.error("Instagram credentials not configured")
                return False
                
            if self.loader is None:
                self.loader = instaloader.Instaloader()
                
            # Try to login
            self.loader.login(self.instagram_username, self.instagram_password)
            logging.info("Successfully logged in to Instagram")
            return True
            
        except BadCredentialsException as e:
            logging.error(f"Bad credentials: {str(e)}")
            return False
        except ConnectionException as e:
            logging.error(f"Connection error during login: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Error during login: {str(e)}")
            return False
            
    def check_direct_scrape(self):
        """Check Instagram using instaloader"""
        # Skip API check if we're not using it
        if not self.use_api:
            logging.info("API access disabled, skipping direct scrape")
            return None
            
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
            
            # Get user profile
            profile = instaloader.Profile.from_username(self.loader.context, self.instagram_username)
            
            # Get latest post
            posts = list(profile.get_posts())
            if not posts:
                logging.warning("No posts found")
                return None
                
            latest_post = posts[0]
            
            post_id = str(latest_post.mediaid)
            if not post_id:
                logging.error("Post ID is missing")
                return None
                
            latest_known_id = get_latest_post_id()
            
            if latest_known_id and post_id == latest_known_id:
                return None
                
            # Create post data
            post_data = {
                'post_id': post_id,
                'date': latest_post.date.isoformat(),
                'caption': latest_post.caption if latest_post.caption else '',
                'url': f"https://www.instagram.com/p/{latest_post.shortcode}/",
                'is_video': latest_post.is_video,
                'video_url': latest_post.video_url if latest_post.is_video else None,
                'thumbnail_url': latest_post.url,
                'source': 'api'
            }
            
            save_post(post_data)
            return post_data
            
        except LoginRequiredException as e:
            logging.error(f"Login required: {str(e)}")
            self.loader = None  # Reset loader to force re-login
            return None
        except ConnectionException as e:
            logging.error(f"Connection error: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in API fetch: {str(e)}")
            return None
            
    def check_rss_feed(self):
        """Check Instagram RSS feed for new posts"""
        try:
            if not self.rss_url:
                logging.error("RSS URL not configured")
                return None
                
            logging.info(f"Checking RSS feed: {self.rss_url}")
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
                logging.info("No new posts found in RSS feed")
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
            
            logging.info(f"New post found in RSS feed: {post_data['url']}")
            save_post(post_data)
            return post_data
            
        except Exception as e:
            logging.error(f"Error checking RSS feed: {str(e)}")
            return None
            
    def get_latest_post(self):
        """Get the latest post using RSS feed first, then API as fallback"""
        # Try RSS first
        post = self.check_rss_feed()
        if post:
            return post
            
        # If RSS fails, try API as fallback (if enabled)
        if self.use_api:
            return self.check_direct_scrape()
            
        return None
        
    def get_post_history(self, limit=10):
        """Get post history from database"""
        try:
            return get_post_history(limit)
        except Exception as e:
            logging.error(f"Error getting post history: {str(e)}")
            return [] 