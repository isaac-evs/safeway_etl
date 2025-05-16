import feedparser
import asyncio
import logging
from datetime import datetime
import aiohttp
from config import RSS_FEEDS, POLLING_INTERVAL, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

class FeedFetcher:
    def __init__(self, db):
        # Store feed URLs and database handle
        self.feeds = RSS_FEEDS
        self.db = db
        self.processed_urls = set()
        self.session = None

        # Common headers to avoid 403 responses
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/90.0.4430.93 Safari/537.36'
            ),
            'Accept': 'application/rss+xml, application/xml;q=0.9, */*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': ''  # will set dynamically
        }

    async def initialize(self):
        # Initialize HTTP session with default headers and persistent connector
        connector = aiohttp.TCPConnector(limit=10, force_close=False)
        self.session = aiohttp.ClientSession(connector=connector, headers=self.headers)
        self.processed_urls = self.db.get_processed_urls() or set()
        logger.info(f"Initialized feed fetcher with {len(self.processed_urls)} existing articles")

    async def close(self):
        if self.session:
            await self.session.close()

    async def fetch_feed(self, feed_url):
        # Validate URL format
        if not feed_url.startswith('http'):
            logger.error(f"Invalid feed URL: {feed_url}")
            return None

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Update Referer dynamically to feed's domain
                self.session.headers['Referer'] = feed_url.rsplit('/', 1)[0]

                async with self.session.get(feed_url, timeout=30) as response:
                    status = response.status
                    if status == 200:
                        # Read raw bytes and let feedparser handle encoding
                        raw = await response.read()
                        return feedparser.parse(raw)
                    elif status == 403:
                        logger.warning(f"403 Forbidden for {feed_url} (attempt {attempt})")
                    else:
                        logger.warning(f"Unexpected status {status} fetching {feed_url} (attempt {attempt})")
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching {feed_url} (attempt {attempt})")
            except aiohttp.ClientError as e:
                logger.error(f"Client error fetching {feed_url} on attempt {attempt}: {e}")
                last_error = e
            except Exception as e:
                logger.exception(f"Unhandled error fetching {feed_url} on attempt {attempt}: {e}")
                last_error = e

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

        logger.error(f"Failed to fetch feed after {MAX_RETRIES} attempts: {feed_url}. Last error: {last_error}")
        return None

    async def fetch_all_feeds(self):
        tasks = [self.fetch_feed(feed) for feed in self.feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_articles = []
        for idx, result in enumerate(results):
            feed_url = self.feeds[idx]
            if isinstance(result, Exception):
                logger.error(f"Exception fetching feed {feed_url}: {result}")
                continue
            if not result or not hasattr(result, 'entries'):
                continue

            source_name = getattr(result.feed, 'title', feed_url)
            for entry in result.entries:
                article = self._parse_entry(entry, source_name)
                if article and article['url'] not in self.processed_urls:
                    new_articles.append(article)
                    self.processed_urls.add(article['url'])

        logger.info(f"Fetched {len(new_articles)} new articles from {len(self.feeds)} feeds")
        return new_articles

    def _parse_entry(self, entry, source_name):
        try:
            url = getattr(entry, 'link', None)
            if not url:
                return None

            # Parse publication date
            published = None
            for field in ('published_parsed', 'updated_parsed'):
                struct_time = getattr(entry, field, None)
                if struct_time:
                    published = datetime(*struct_time[:6]).date()
                    break

            # Fallback to string fields
            if not published:
                for field in ('published', 'pubDate', 'updated'):
                    date_str = getattr(entry, field, None)
                    if date_str:
                        try:
                            published = datetime.fromisoformat(date_str).date()
                            break
                        except Exception:
                            continue

            if not published:
                published = datetime.utcnow().date()

            title = getattr(entry, 'title', None)
            description = None
            for desc in ('description', 'summary', 'content'):
                val = getattr(entry, desc, None)
                if val:
                    description = val
                    break

            # Normalize content lists
            if isinstance(description, list):
                description = ''.join(
                    item.get('value', '') for item in description if isinstance(item, dict)
                )

            if not title or not description:
                return None

            return {
                'news_source': source_name,
                'title': title,
                'description': description,
                'url': url,
                'date': published
            }
        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None

    async def poll_feeds_continuously(self, article_queue):
        try:
            await self.initialize()
            while True:
                try:
                    new_articles = await self.fetch_all_feeds()
                    for article in new_articles:
                        await article_queue.put(article)
                    logger.info(f"Queued {len(new_articles)} new articles")
                except Exception as e:
                    logger.error(f"Polling cycle error: {e}")
                finally:
                    await asyncio.sleep(POLLING_INTERVAL)
        finally:
            await self.close()
