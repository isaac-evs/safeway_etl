import asyncio
import logging
import signal
import sys

from database import Database
from feed_fetcher import FeedFetcher
from article_processor import ArticleProcessor
from geocoder import Geocoder
from config import POLLING_INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mexico_news_etl.log')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    db = Database()
    db.initialize_db()

    article_queue = asyncio.Queue()

    feed_fetcher = FeedFetcher(db)
    article_processor = ArticleProcessor()
    geocoder = Geocoder()

    await geocoder.initialize()

    try:
        feed_task = asyncio.create_task(feed_fetcher.poll_feeds_continuously(article_queue))

        worker_tasks = []
        num_workers = 3
        for _ in range(num_workers):
            worker_task = asyncio.create_task(article_processor.process_articles(article_queue, geocoder, db))
            worker_tasks.append(worker_task)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(feed_task, worker_tasks, geocoder)))

        await feed_task
    except Exception as e:
        logger.error(f"Error in main process: {e}")
    finally:
        await geocoder.close()

async def shutdown(feed_task, worker_tasks, geocoder):
    """Graceful shutdown procedure"""
    logger.info("Shutting down...")

    feed_task.cancel()

    try:
        await asyncio.wait_for(feed_task, timeout=5)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    for task in worker_tasks:
        task.cancel()


    await asyncio.gather(*worker_tasks, return_exceptions=True)

    await geocoder.close()

    sys.exit(0)

if __name__ == "__main__":
    logger.info("Starting Mexico News ETL Pipeline")
    asyncio.run(main())
