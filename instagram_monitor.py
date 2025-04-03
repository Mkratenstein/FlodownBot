import feedparser
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv
import time
import requests
import json
from requests.exceptions import RequestException, ConnectionError, Timeout, HTTPError
from json.decoder import JSONDecodeError
from urllib.parse import urlparse

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
load_dotenv()

class InstagramMonitor:
    def __init__(self):
        self.rss_url = os.getenv('INSTAGRAM_RSS_URL')
        self.instagram_username = os.getenv('INSTAGRAM_USERNAME', 'goosetheband')
        self.instagram_password = os.getenv('INSTAGRAM_PASSWORD')
        self.access_token = None
        self.token_expiry = None
        self.last_scrape_attempt = 0
        self.scrape_cooldown = 300  # 5 minutes cooldown between scrape attempts
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        init_db()
        
    def _get_access_token(self):
        """Get Instagram access token using username and password"""
        try:
            if not self.instagram_username or not self.instagram_password:
                logging.error("Instagram credentials not configured")
                return None
                
            # Instagram login endpoint
            login_url = 'https://www.instagram.com/accounts/login/ajax/'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Instagram-AJAX': '1',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.instagram.com',
                'Referer': 'https://www.instagram.com/'
            }
            
            # First get the CSRF token
            session = requests.Session()
            response = session.get('https://www.instagram.com/')
            csrf = response.cookies['csrftoken']
            headers['X-CSRFToken'] = csrf
            
            # Login data
            login_data = {
                'username': self.instagram_username,
                'password': self.instagram_password,
                'queryParams': '{}',
                'optIntoOneTap': 'false'
            }
            
            # Perform login
            response = session.post(login_url, data=login_data, headers=headers)
            response.raise_for_status()
            
            # Get the access token from the response
            if response.json().get('authenticated'):
                # Extract access token from shared data
                shared_data = response.json().get('sharedData', {})
                if shared_data:
                    self.access_token = shared_data.get('accessToken')
                    self.token_expiry = time.time() + 3600  # Token expires in 1 hour
                    logging.info("Successfully obtained Instagram access token")
                    return self.access_token
                    
            logging.error("Failed to authenticate with Instagram")
            return None
            
        except Exception as e:
            logging.error(f"Error getting Instagram access token: {str(e)}")
            return None
            
    def _validate_url(self, url):
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logging.error(f"Invalid URL format: {url} - {str(e)}")
            return False
            
    def _make_request(self, url, headers=None, retry_count=0):
        """Make HTTP request with retry logic"""
        try:
            if headers is None:
                headers = {}
                
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except ConnectionError as e:
            logging.error(f"Connection error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, headers, retry_count + 1)
            raise
        except Timeout as e:
            logging.error(f"Timeout error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, headers, retry_count + 1)
            raise
        except HTTPError as e:
            logging.error(f"HTTP error for URL {url}: {str(e)}")
            if retry_count < self.max_retries and e.response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(self.retry_delay)
                return self._make_request(url, headers, retry_count + 1)
            raise
        except RequestException as e:
            logging.error(f"Request error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, headers, retry_count + 1)
            raise
            
    def check_direct_scrape(self):
        """Check Instagram using their Graph API"""
        try:
            # Check if we need to wait before trying again
            current_time = time.time()
            if current_time - self.last_scrape_attempt < self.scrape_cooldown:
                logging.info("Waiting for scrape cooldown period...")
                return None
                
            self.last_scrape_attempt = current_time
            logging.info("Attempting Instagram Graph API fetch...")
            
            # Check if we need to refresh the access token
            if not self.access_token or (self.token_expiry and current_time >= self.token_expiry):
                self.access_token = self._get_access_token()
                if not self.access_token:
                    logging.error("Failed to get Instagram access token")
                    return None
            
            # Get user profile data
            profile_url = f'https://www.instagram.com/api/v1/users/web_profile_info/?username={self.instagram_username}'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = self._make_request(profile_url, headers)
            data = response.json()
            
            if not data.get('data', {}).get('user', {}).get('edge_owner_to_timeline_media', {}).get('edges'):
                logging.warning("No posts found in API response")
                return None
                
            latest_post = data['data']['user']['edge_owner_to_timeline_media']['edges'][0]['node']
            
            post_id = str(latest_post.get('id'))
            if not post_id:
                logging.error("Post ID is missing from API response")
                return None
                
            latest_known_id = get_latest_post_id()
            
            if latest_known_id and post_id == latest_known_id:
                return None
                
            # Create post data with validation
            post_data = {
                'post_id': post_id,
                'date': datetime.fromtimestamp(latest_post.get('taken_at_timestamp', time.time())).isoformat(),
                'caption': latest_post.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                'url': f"https://www.instagram.com/p/{latest_post.get('shortcode', '')}/",
                'is_video': latest_post.get('is_video', False),
                'video_url': latest_post.get('video_url'),
                'thumbnail_url': latest_post.get('display_url', ''),
                'source': 'api'
            }
            
            # Validate post data
            if not self._validate_url(post_data['url']):
                logging.error(f"Invalid post URL: {post_data['url']}")
                return None
                
            if not post_data['thumbnail_url'] and not post_data['video_url']:
                logging.error("No media content found in post")
                return None
            
            save_post(post_data)
            return post_data
            
        except ValueError as e:
            logging.error(f"Validation error: {str(e)}")
            return None
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "401" in error_msg:  # Rate limit or unauthorized
                logging.warning("Instagram rate limit hit, will try again later")
                self.access_token = None  # Force token refresh on next attempt
            else:
                logging.error(f"Unexpected error in API fetch: {error_msg}")
            return None
            
    def check_rss_feed(self):
        """Check Instagram RSS feed for new posts"""
        try:
            if not self._validate_url(self.rss_url):
                raise ValueError(f"Invalid RSS URL: {self.rss_url}")
                
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
                
            # Create post data from RSS entry with validation
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
            
            # Validate post data
            if not self._validate_url(post_data['url']):
                logging.error(f"Invalid post URL: {post_data['url']}")
                return None
                
            if not post_data['thumbnail_url']:
                logging.error("No media content found in RSS entry")
                return None
            
            save_post(post_data)
            return post_data
            
        except ValueError as e:
            logging.error(f"Validation error: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error checking RSS feed: {str(e)}")
            return None
            
    def get_latest_post(self):
        """Get the latest post using Graph API first, then RSS as fallback"""
        # Try Graph API first
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