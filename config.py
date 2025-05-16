import os
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-2')

MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
CLAUDE_MODEL_ID = os.getenv('CLAUDE_MODEL_ID', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'news_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

POLLING_INTERVAL = int(os.getenv('POLLING_INTERVAL', 7200))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
RETRY_DELAY = int(os.getenv('RETRY_DELAY', 10))

default_feeds = 'https://www.mural.com.mx/rss/portada.xml,https://www.elnorte.com/rss/portada.xml,https://www.jornada.com.mx/rss/estados.xml?v=1'
RSS_FEEDS = os.getenv('RSS_FEEDS', default_feeds).split(',')

VALID_CATEGORIES = ['crime', 'infrastructure', 'hazard', 'social']
