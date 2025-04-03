import feedparser
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv
import time
import instaloader
from instaloader.exceptions import ConnectionException, BadCredentialsException, LoginRequiredException
import threading
import queue
import concurrent.futures
import re

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

# Create a thread pool for concurrent operations
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

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
        self.lock = threading.Lock()  # Lock for thread safety
        self.cache = {}  # Simple cache for API responses
        self.cache_timeout = 300  # 5 minutes cache timeout
        
        # Initialize database
        init_db()
        
        # Check if we should try using the API
        if self.instagram_username and self.instagram_password:
            self.use_api = True
            logging.info("Instagram credentials found, will attempt API access")
        else:
            logging.info("No Instagram credentials found, will use RSS feed only")
        
    def _login(self):
        """Login to Instagram using instaloader"""
        with self.lock:  # Ensure thread safety
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
            
    def _get_cached_data(self, key):
        """Get data from cache if it exists and is not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_timeout:
                return data
        return None
        
    def _set_cached_data(self, key, data):
        """Set data in cache with current timestamp"""
        self.cache[key] = (data, time.time())
            
    def check_direct_scrape(self):
        """Check Instagram using instaloader"""
        # Skip API check if we're not using it
        if not self.use_api:
            logging.info("API access disabled, skipping direct scrape")
            return None
            
        # Check cache first
        cache_key = f"api_posts_{self.instagram_username}"
        cached_data = self._get_cached_data(cache_key)
        if cached_data:
            logging.info("Using cached API data")
            return cached_data
            
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
                # Cache the result even if it's not new
                self._set_cached_data(cache_key, None)
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
            
            # Cache the result
            self._set_cached_data(cache_key, post_data)
            
            # Save to database
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
        # Check cache first
        cache_key = "rss_feed"
        cached_data = self._get_cached_data(cache_key)
        if cached_data:
            logging.info("Using cached RSS data")
            return cached_data
            
        try:
            if not self.rss_url:
                logging.error("RSS URL not configured")
                return None
                
            logging.info(f"Checking RSS feed: {self.rss_url}")
            feed = feedparser.parse(self.rss_url)
            
            if not feed.entries:
                logging.warning("No entries found in RSS feed")
                self._set_cached_data(cache_key, None)
                return None
                
            latest_entry = feed.entries[0]
            
            # Extract post ID from link or guid
            post_id = latest_entry.get('id', '') or latest_entry.get('guid', '') or latest_entry.get('link', '')
            if not post_id:
                logging.error("Post ID is missing from RSS entry")
                return None
                
            # Check if this is a new post
            latest_known_id = get_latest_post_id()
            if latest_known_id and post_id == latest_known_id:
                logging.info("No new posts found in RSS feed")
                self._set_cached_data(cache_key, None)
                return None
                
            # Extract media content safely
            media_content = latest_entry.get('media_content', [])
            thumbnail_url = ''
            if media_content and isinstance(media_content, list) and len(media_content) > 0:
                thumbnail_url = media_content[0].get('url', '')
            
            # Clean up the description/caption
            description = latest_entry.get('description', '') or latest_entry.get('title', '')
            
            # Remove HTML tags and clean up the text
            # Remove HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            # Remove multiple spaces and newlines
            description = re.sub(r'\s+', ' ', description).strip()
            
            # Format the date
            published_date = latest_entry.get('published', datetime.now().isoformat())
            try:
                # Parse the date string
                parsed_date = datetime.strptime(published_date, "%a, %d %b %Y %H:%M:%S %z")
                # Format it nicely
                formatted_date = parsed_date.strftime("%m/%d/%Y %I:%M %p")
            except:
                formatted_date = datetime.now().strftime("%m/%d/%Y %I:%M %p")
            
            # Create post data from RSS entry with safe defaults
            post_data = {
                'post_id': post_id,
                'date': published_date,
                'caption': description,
                'url': latest_entry.get('link', ''),
                'is_video': False,  # RSS doesn't provide this info
                'video_url': None,
                'thumbnail_url': thumbnail_url,
                'source': 'rss',
                'likes': 0,  # Default to 0 since RSS doesn't provide this
                'comments': 0,  # Default to 0 since RSS doesn't provide this
                'formatted_date': formatted_date  # Add formatted date for display
            }
            
            logging.info(f"New post found in RSS feed: {post_data['url']}")
            
            # Cache the result
            self._set_cached_data(cache_key, post_data)
            
            # Save to database
            save_post(post_data)
            return post_data
            
        except Exception as e:
            logging.error(f"Error checking RSS feed: {str(e)}", exc_info=True)  # Added exc_info for better debugging
            return None
            
    def get_latest_post(self):
        """Get the latest post using RSS feed first, then API as fallback"""
        # Try both methods concurrently
        futures = []
        
        # Always try RSS first
        futures.append(thread_pool.submit(self.check_rss_feed))
        
        # Try API as fallback if enabled
        if self.use_api:
            futures.append(thread_pool.submit(self.check_direct_scrape))
            
        # Wait for the first successful result
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    return result
            except Exception as e:
                logging.error(f"Error in concurrent fetch: {str(e)}")
                
        return None
        
    def get_post_history(self, limit=10):
        """Get post history from database"""
        try:
            return get_post_history(limit)
        except Exception as e:
            logging.error(f"Error getting post history: {str(e)}")
            return [] 