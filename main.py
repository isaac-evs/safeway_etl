import asyncio
import logging
import sys
import json
import boto3
import os

from database import Database
from feed_fetcher import FeedFetcher
from article_processor import ArticleProcessor
from geocoder import Geocoder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function to get parameters from SSM Parameter Store
def get_parameters():
    """
    Retrieve parameters from AWS Systems Manager Parameter Store
    """
    try:
        # Get the environment (dev, stage, prod)
        env = os.environ.get('ENVIRONMENT', 'dev')

        # Use the AWS region from Lambda's environment
        # (Lambda automatically sets AWS_REGION for us)
        region = os.environ.get('AWS_REGION', 'us-east-2')

        # Path prefix for our parameters
        path = f"/mexico-news-etl/{env}/"

        logger.info(f"Getting parameters from {path} in region {region}")

        # Initialize SSM client with the region
        ssm = boto3.client('ssm', region_name=region)

        # Get all parameters by path with decryption
        response = ssm.get_parameters_by_path(
            Path=path,
            Recursive=True,
            WithDecryption=True
        )

        # Create a dictionary of parameters
        parameters = {}
        for param in response['Parameters']:
            # Extract the parameter name without the path prefix
            name = param['Name'].replace(path, '')
            parameters[name] = param['Value']

        # Continue fetching if there are more parameters (pagination)
        while 'NextToken' in response:
            response = ssm.get_parameters_by_path(
                Path=path,
                Recursive=True,
                WithDecryption=True,
                NextToken=response['NextToken']
            )

            for param in response['Parameters']:
                name = param['Name'].replace(path, '')
                parameters[name] = param['Value']

        logger.info(f"Retrieved {len(parameters)} parameters from SSM Parameter Store")

        # Make sure we set AWS_REGION in the parameters
        if 'AWS_REGION' not in parameters:
            parameters['AWS_REGION'] = region

        return parameters

    except Exception as e:
        logger.error(f"Error retrieving parameters: {e}")
        # For critical parameters, we might want to raise the exception
        # For now, return an empty dict to allow fallback to environment variables
        return {}

# Lambda handler function
def lambda_handler(event, context):
    logger.info("Starting Mexico News ETL Pipeline in Lambda")

    try:
        # Get parameters from SSM Parameter Store
        params = get_parameters()

        # Set parameters as environment variables for the rest of the application
        # (This approach avoids modifying the rest of your code)
        for key, value in params.items():
            if key and value:  # Ensure we're not setting empty values
                os.environ[key] = value

        # Run the async event loop
        asyncio.run(main_process())
        return {
            'statusCode': 200,
            'body': json.dumps('ETL Pipeline executed successfully')
        }
    except Exception as e:
        logger.error(f"Error in Lambda execution: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

async def main_process():
    """Main async process for Lambda execution"""
    db = Database()
    db.initialize_db()

    article_queue = asyncio.Queue()

    feed_fetcher = FeedFetcher(db)
    article_processor = ArticleProcessor()
    geocoder = Geocoder()

    await geocoder.initialize()

    try:
        # Fetch articles
        await feed_fetcher.initialize()
        new_articles = await feed_fetcher.fetch_all_feeds()
        for article in new_articles:
            await article_queue.put(article)

        # Process the articles
        tasks = []
        num_workers = 3
        for _ in range(num_workers):
            task = asyncio.create_task(article_processor.process_articles(article_queue, geocoder, db))
            tasks.append(task)

        # Wait for all articles to be processed
        await article_queue.join()

        # Cancel worker tasks
        for task in tasks:
            task.cancel()

        # Wait for tasks to be cancelled
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        logger.error(f"Error in main process: {e}")
    finally:
        await geocoder.close()
        if hasattr(feed_fetcher, 'session') and feed_fetcher.session:
            await feed_fetcher.close()

# Keep the original main function for local testing
async def main():
    db = Database()
    db.initialize_db()

    article_queue = asyncio.Queue()

    feed_fetcher = FeedFetcher(db)
    article_processor = ArticleProcessor()
    geocoder = Geocoder()

    await geocoder.initialize()

    try:
        await feed_fetcher.initialize()
        await feed_fetcher.poll_feeds_continuously(article_queue)
    except Exception as e:
        logger.error(f"Error in main process: {e}")
    finally:
        await geocoder.close()
        if hasattr(feed_fetcher, 'session') and feed_fetcher.session:
            await feed_fetcher.close()

if __name__ == "__main__":
    logger.info("Starting Mexico News ETL Pipeline locally")
    asyncio.run(main())
