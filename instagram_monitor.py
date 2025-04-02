import feedparser
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv
import time
import requests
import json
import re
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
        self.last_scrape_attempt = 0
        self.scrape_cooldown = 300  # 5 minutes cooldown between scrape attempts
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        init_db()
        
        # Headers to mimic a web browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'sec-ch-ua': '"Google Chrome";v="91", "Chromium";v="91"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
    def _validate_url(self, url):
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logging.error(f"Invalid URL format: {url} - {str(e)}")
            return False
            
    def _make_request(self, url, session=None, retry_count=0):
        """Make HTTP request with retry logic"""
        if session is None:
            session = requests.Session()
            
        try:
            response = session.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response
        except ConnectionError as e:
            logging.error(f"Connection error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, session, retry_count + 1)
            raise
        except Timeout as e:
            logging.error(f"Timeout error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, session, retry_count + 1)
            raise
        except HTTPError as e:
            logging.error(f"HTTP error for URL {url}: {str(e)}")
            if retry_count < self.max_retries and e.response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(self.retry_delay)
                return self._make_request(url, session, retry_count + 1)
            raise
        except RequestException as e:
            logging.error(f"Request error for URL {url}: {str(e)}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self._make_request(url, session, retry_count + 1)
            raise
            
    def check_direct_scrape(self):
        """Check Instagram using their public API"""
        try:
            # Check if we need to wait before trying again
            current_time = time.time()
            if current_time - self.last_scrape_attempt < self.scrape_cooldown:
                logging.info("Waiting for scrape cooldown period...")
                return None
                
            self.last_scrape_attempt = current_time
            logging.info("Attempting Instagram public API fetch...")
            
            # First, get the user page to extract additional required data
            profile_url = f'https://www.instagram.com/{self.instagram_username}/'
            if not self._validate_url(profile_url):
                raise ValueError(f"Invalid profile URL: {profile_url}")
                
            session = requests.Session()
            response = self._make_request(profile_url, session)
            
            # Extract the shared data JSON
            shared_data_match = re.search(r'<script type="text/javascript">window._sharedData = (.+?);</script>', response.text)
            if not shared_data_match:
                logging.warning("Could not find shared data in profile page")
                return None
                
            try:
                shared_data = json.loads(shared_data_match.group(1))
            except JSONDecodeError as e:
                logging.error(f"Failed to parse shared data JSON: {str(e)}")
                return None
                
            try:
                user_id = shared_data['entry_data']['ProfilePage'][0]['graphql']['user']['id']
            except (KeyError, IndexError) as e:
                logging.error(f"Failed to extract user ID from shared data: {str(e)}")
                return None
            
            # Now fetch the latest posts using public API
            api_url = f'https://www.instagram.com/api/v1/feed/user/{user_id}/username/?count=1'
            if not self._validate_url(api_url):
                raise ValueError(f"Invalid API URL: {api_url}")
                
            response = self._make_request(api_url, session)
            
            try:
                data = response.json()
            except JSONDecodeError as e:
                logging.error(f"Failed to parse API response JSON: {str(e)}")
                return None
                
            if not data.get('items'):
                logging.warning("No posts found in API response")
                return None
                
            latest_post = data['items'][0]
            
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
                'date': datetime.fromtimestamp(latest_post.get('taken_at', time.time())).isoformat(),
                'caption': latest_post.get('caption', {}).get('text', '') if latest_post.get('caption') else '',
                'url': f"https://www.instagram.com/p/{latest_post.get('code', '')}/",
                'is_video': latest_post.get('is_video', False),
                'video_url': latest_post.get('video_versions', [{}])[0].get('url') if latest_post.get('is_video') else None,
                'thumbnail_url': latest_post.get('image_versions2', {}).get('candidates', [{}])[0].get('url', ''),
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
                self.scrape_cooldown = min(self.scrape_cooldown * 2, 1800)  # Max 30 minutes
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
        """Get the latest post using public API first, then RSS as fallback"""
        # Try public API first
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