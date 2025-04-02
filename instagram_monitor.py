import feedparser
from instaloader import Instaloader, Profile
import logging
from datetime import datetime
from database import init_db, get_latest_post_id, save_post, get_post_history
import os
from dotenv import load_dotenv

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
        self.loader = Instaloader()
        init_db()
        
    def check_direct_scrape(self):
        """Check Instagram directly using instaloader"""
        try:
            profile = Profile.from_username(self.loader.context, self.instagram_username)
            latest_post = next(profile.get_posts())
            
            post_id = str(latest_post.mediaid)
            latest_known_id = get_latest_post_id()
            
            if latest_known_id and post_id == latest_known_id:
                return None
                
            post_data = {
                'post_id': post_id,
                'date': latest_post.date_local.isoformat(),
                'caption': latest_post.caption,
                'url': latest_post.url,
                'is_video': latest_post.is_video,
                'video_url': latest_post.video_url if latest_post.is_video else None,
                'thumbnail_url': latest_post.url,
                'source': 'direct'
            }
            
            save_post(post_data)
            return post_data
            
        except Exception as e:
            logging.error(f"Error in direct scraping: {str(e)}")
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
        """Get the latest post using direct scraping first, then RSS as fallback"""
        # Try direct scraping first
        post = self.check_direct_scrape()
        if post:
            return post
            
        # If direct scraping fails, try RSS as fallback
        return self.check_rss_feed()
        
    def get_post_history(self, limit=10):
        """Get post history from database"""
        return get_post_history(limit) 