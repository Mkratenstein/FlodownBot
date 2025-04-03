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
import random
import hashlib
import hmac

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
        self.session = requests.Session()
        self.last_scrape_attempt = 0
        self.scrape_cooldown = 300  # 5 minutes cooldown between scrape attempts
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        init_db()
        
        # Set up session headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '198387',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Referer': 'https://www.instagram.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Upgrade-Insecure-Requests': '1'
        })
        
    def _get_csrf_token(self):
        """Get CSRF token from Instagram"""
        try:
            response = self.session.get('https://www.instagram.com/')
            if 'csrftoken' in response.cookies:
                return response.cookies['csrftoken']
            return None
        except Exception as e:
            logging.error(f"Error getting CSRF token: {str(e)}")
            return None
            
    def _generate_device_id(self):
        """Generate a device ID for Instagram"""
        return f"android-{hashlib.md5(str(time.time()).encode()).hexdigest()[:16]}"
        
    def _generate_signature(self, data):
        """Generate signature for Instagram API requests"""
        return hmac.new(
            b'9193488027538fd3450b83b7d05286d4',
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
    def _login(self):
        """Login to Instagram"""
        try:
            if not self.instagram_username or not self.instagram_password:
                logging.error("Instagram credentials not configured")
                return False
                
            # Get CSRF token
            csrf_token = self._get_csrf_token()
            if not csrf_token:
                logging.error("Failed to get CSRF token")
                return False
                
            # Update headers with CSRF token
            self.session.headers.update({
                'X-CSRFToken': csrf_token
            })
            
            # First, get the login page to get additional cookies
            self.session.get('https://www.instagram.com/accounts/login/')
            
            # Generate device ID
            device_id = self._generate_device_id()
            
            # Prepare login data
            login_data = {
                'username': self.instagram_username,
                'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{self.instagram_password}',
                'queryParams': '{}',
                'optIntoOneTap': 'false',
                'stopDeletionNonce': '',
                'trustedDeviceRecords': '{}',
                'device_id': device_id
            }
            
            # Add signature
            signature = self._generate_signature(json.dumps(login_data))
            login_data['signature'] = signature
            
            # Perform login
            login_url = 'https://www.instagram.com/api/v1/web/accounts/login/ajax/'
            response = self.session.post(login_url, data=login_data)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('authenticated'):
                    logging.info("Successfully logged in to Instagram")
                    return True
                elif data.get('spam'):
                    logging.error("Instagram detected suspicious activity. Please try again later.")
                    return False
                elif data.get('checkpoint_required'):
                    logging.error("Instagram requires additional verification. Please log in manually first.")
                    return False
                    
            logging.error(f"Login failed: {response.text}")
            return False
            
        except Exception as e:
            logging.error(f"Error during login: {str(e)}")
            return False
            
    def _validate_url(self, url):
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logging.error(f"Invalid URL format: {url} - {str(e)}")
            return False
            
    def _make_request(self, url, method='GET', data=None, retry_count=0):
        """Make HTTP request with retry logic"""
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=10)
            else:
                response = self.session.post(url, data=data, timeout=10)
                
            response.raise_for_status()
            return response
        except ConnectionError as e:
            logging.error(f"Connection error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, method, data, retry_count + 1)
            raise
        except Timeout as e:
            logging.error(f"Timeout error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, method, data, retry_count + 1)
            raise
        except HTTPError as e:
            logging.error(f"HTTP error for URL {url}: {str(e)}")
            if retry_count < self.max_retries and e.response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(self.retry_delay)
                return self._make_request(url, method, data, retry_count + 1)
            raise
        except RequestException as e:
            logging.error(f"Request error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, method, data, retry_count + 1)
            raise
            
    def check_direct_scrape(self):
        """Check Instagram using their API"""
        try:
            # Check if we need to wait before trying again
            current_time = time.time()
            if current_time - self.last_scrape_attempt < self.scrape_cooldown:
                logging.info("Waiting for scrape cooldown period...")
                return None
                
            self.last_scrape_attempt = current_time
            logging.info("Attempting Instagram API fetch...")
            
            # Ensure we're logged in
            if not self._login():
                logging.error("Failed to login to Instagram")
                return None
            
            # Get user profile data
            profile_url = f'https://www.instagram.com/api/v1/users/web_profile_info/?username={self.instagram_username}'
            response = self._make_request(profile_url)
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
                self.session = requests.Session()  # Reset session on rate limit
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