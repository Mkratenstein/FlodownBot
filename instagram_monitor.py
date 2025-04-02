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
        init_db()
        
        # Headers to mimic a web browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
    def check_direct_scrape(self):
        """Check Instagram using their GraphQL API"""
        try:
            # Check if we need to wait before trying again
            current_time = time.time()
            if current_time - self.last_scrape_attempt < self.scrape_cooldown:
                logging.info("Waiting for scrape cooldown period...")
                return None
                
            self.last_scrape_attempt = current_time
            logging.info("Attempting Instagram GraphQL fetch...")
            
            # First, get the user page to extract additional required data
            profile_url = f'https://www.instagram.com/{self.instagram_username}/'
            response = requests.get(profile_url, headers=self.headers)
            
            if response.status_code != 200:
                logging.warning(f"Failed to fetch profile page: {response.status_code}")
                return None
                
            # Extract the shared data JSON
            shared_data_match = re.search(r'<script type="text/javascript">window._sharedData = (.+?);</script>', response.text)
            if not shared_data_match:
                logging.warning("Could not find shared data in profile page")
                return None
                
            shared_data = json.loads(shared_data_match.group(1))
            user_id = shared_data['entry_data']['ProfilePage'][0]['graphql']['user']['id']
            
            # Now fetch the latest posts using GraphQL API
            variables = {
                'id': user_id,
                'first': 1  # Only get the most recent post
            }
            
            graphql_url = f'https://www.instagram.com/graphql/query/?query_hash=003056d32c2554def87228bc3fd9668a&variables={json.dumps(variables)}'
            response = requests.get(graphql_url, headers=self.headers)
            
            if response.status_code != 200:
                logging.warning(f"Failed to fetch GraphQL data: {response.status_code}")
                return None
                
            data = response.json()
            latest_post = data['data']['user']['edge_owner_to_timeline_media']['edges'][0]['node']
            
            post_id = str(latest_post['id'])
            latest_known_id = get_latest_post_id()
            
            if latest_known_id and post_id == latest_known_id:
                return None
                
            # Create post data
            post_data = {
                'post_id': post_id,
                'date': datetime.fromtimestamp(latest_post['taken_at_timestamp']).isoformat(),
                'caption': latest_post['edge_media_to_caption']['edges'][0]['node']['text'] if latest_post['edge_media_to_caption']['edges'] else '',
                'url': f"https://www.instagram.com/p/{latest_post['shortcode']}/",
                'is_video': latest_post['is_video'],
                'video_url': latest_post.get('video_url'),
                'thumbnail_url': latest_post['display_url'],
                'source': 'graphql'
            }
            
            save_post(post_data)
            return post_data
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:  # Too Many Requests
                logging.warning("Instagram rate limit hit, will try again later")
                self.scrape_cooldown = min(self.scrape_cooldown * 2, 1800)  # Max 30 minutes
            else:
                logging.error(f"Error in GraphQL fetch: {error_msg}")
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
        """Get the latest post using GraphQL first, then RSS as fallback"""
        # Try GraphQL first
        post = self.check_direct_scrape()
        if post:
            return post
            
        # If GraphQL fails, try RSS as fallback
        return self.check_rss_feed()
        
    def get_post_history(self, limit=10):
        """Get post history from database"""
        return get_post_history(limit) 