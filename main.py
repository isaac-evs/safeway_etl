import asyncio
import logging
import signal
import sys
import json
import boto3
import os
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# This version of get_parameters is more robust and handles the case where
# the Lambda doesn't have describe_parameters permission
def get_parameters():
    """
    Retrieve parameters from AWS Systems Manager Parameter Store
    with better error handling for permission issues
    """
    try:
        # Get the environment (dev, stage, prod)
        env = os.environ.get('ENVIRONMENT', 'dev')

        # Use the AWS region from Lambda's environment
        region = os.environ.get('AWS_REGION', 'us-east-2')

        # Log current environment variables
        logger.info(f"Current environment variables: ENVIRONMENT={env}, AWS_REGION={region}")

        # Try both path formats
        paths_to_try = [
            f"/mexico-news-etl/{env}/",  # With leading slash
            f"mexico-news-etl/{env}/"    # Without leading slash
        ]

        # Initialize SSM client with the region
        ssm = boto3.client('ssm', region_name=region)
        logger.info(f"Initialized SSM client in region: {region}")

        # Try each path format until we find parameters
        parameters = {}
        success = False

        for path in paths_to_try:
            logger.info(f"Trying to get parameters from path: {path}")

            try:
                response = ssm.get_parameters_by_path(
                    Path=path,
                    Recursive=True,
                    WithDecryption=True
                )

                params_count = len(response.get('Parameters', []))
                logger.info(f"Found {params_count} parameters at path: {path}")

                if params_count > 0:
                    # Process the parameters
                    for param in response.get('Parameters', []):
                        # Extract the parameter name without the path prefix
                        name = param['Name'].replace(path, '')
                        # Remove any remaining path segments if present
                        if '/' in name:
                            name = name.split('/')[-1]

                        parameters[name] = param['Value']

                        # Log parameter retrieval (but redact sensitive values)
                        if name in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'DB_PASSWORD', 'MAPBOX_ACCESS_TOKEN']:
                            logger.info(f"Retrieved parameter: {name} = [REDACTED]")
                        else:
                            logger.info(f"Retrieved parameter: {name} = {param['Value']}")

                    # Continue fetching if there are more parameters (pagination)
                    while 'NextToken' in response:
                        response = ssm.get_parameters_by_path(
                            Path=path,
                            Recursive=True,
                            WithDecryption=True,
                            NextToken=response['NextToken']
                        )

                        for param in response.get('Parameters', []):
                            name = param['Name'].replace(path, '')
                            if '/' in name:
                                name = name.split('/')[-1]
                            parameters[name] = param['Value']

                    success = True
                    logger.info(f"Successfully retrieved parameters from path: {path}")
                    break  # Exit the loop once we find parameters

            except Exception as e:
                logger.warning(f"Error getting parameters from path {path}: {e}")

        if not success or not parameters:
            logger.error("Failed to retrieve parameters from any path!")

            # Check if we can see any parameters at all (this might fail due to permissions)
            try:
                # This is an optional check that might fail - we'll continue even if it does
                logger.info("Attempting to list parameters (may fail if no permissions)...")
                params_list = ssm.describe_parameters(MaxResults=10)
                param_count = len(params_list.get('Parameters', []))
                logger.info(f"Found {param_count} parameters in account")
            except Exception as e:
                logger.warning(f"Could not list parameters: {e}")
                logger.warning("This is often due to IAM permission issues")
                logger.warning("The Lambda execution role needs ssm:DescribeParameters, ssm:GetParameter, ssm:GetParameters, and ssm:GetParametersByPath permissions")

            # Manual fallback - we'll define critical parameters with dummy values
            # that will cause the Lambda to fail in a controlled way
            parameters = {
                'DB_HOST': 'PARAMETER_STORE_ACCESS_FAILED',
                'DB_PORT': '5432',
                'DB_NAME': 'news_db',
                'DB_USER': 'postgres',
                'DB_PASSWORD': 'dummy',
                'AWS_REGION': region
            }

            logger.warning("Using fallback parameters that will intentionally fail!")
            return parameters

        # Make sure we set AWS_REGION in the parameters
        if 'AWS_REGION' not in parameters:
            parameters['AWS_REGION'] = region

        logger.info(f"Retrieved {len(parameters)} parameters from SSM Parameter Store")
        return parameters

    except Exception as e:
        logger.error(f"Unexpected error retrieving parameters: {e}")
        logger.error(traceback.format_exc())

        # Fallback with error markers
        return {
            'DB_HOST': 'ERROR_RETRIEVING_PARAMETERS',
            'DB_PORT': '5432',
            'DB_NAME': 'news_db',
            'DB_USER': 'postgres',
            'DB_PASSWORD': 'dummy',
            'AWS_REGION': os.environ.get('AWS_REGION', 'us-east-2')
        }

# Lambda handler function
def lambda_handler(event, context):
    logger.info("Starting Mexico News ETL Pipeline in Lambda")

    try:
        # Get parameters from SSM Parameter Store
        params = get_parameters()

        # Check if we got error parameters
        if params.get('DB_HOST') in ['PARAMETER_STORE_ACCESS_FAILED', 'ERROR_RETRIEVING_PARAMETERS']:
            error_msg = f"Parameter Store access failed: {params.get('DB_HOST')}"
            logger.error(error_msg)
            return {
                'statusCode': 500,
                'body': json.dumps(f'Error: {error_msg}. Check Lambda permissions and SSM Parameter Store setup.')
            }

        # Validate that we have required parameters
        required_params = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
        missing_params = [p for p in required_params if p not in params]

        if missing_params:
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {
                'statusCode': 500,
                'body': json.dumps(f'Error: {error_msg}')
            }

        # Set parameters as environment variables for the rest of the application
        for key, value in params.items():
            if key and value:  # Ensure we're not setting empty values
                os.environ[key] = value
                if key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'DB_PASSWORD', 'MAPBOX_ACCESS_TOKEN']:
                    logger.info(f"Set environment variable: {key} = [REDACTED]")
                else:
                    logger.info(f"Set environment variable: {key} = {value}")

        # For debugging, log database connection parameters
        db_host = os.environ.get('DB_HOST')
        db_port = os.environ.get('DB_PORT')
        db_name = os.environ.get('DB_NAME')
        db_user = os.environ.get('DB_USER')
        logger.info(f"Database connection will use: host={db_host}, port={db_port}, dbname={db_name}, user={db_user}")

        # For testing parameter store only, uncomment this block
        """
        return {
            'statusCode': 200,
            'body': json.dumps('Parameters retrieved successfully: ' +
                               f'host={db_host}, port={db_port}, dbname={db_name}, user={db_user}')
        }
        """

        # Run the async event loop with the ETL logic
        asyncio.run(lambda_main())

        return {
            'statusCode': 200,
            'body': json.dumps('ETL Pipeline executed successfully')
        }
    except Exception as e:
        logger.error(f"Error in Lambda execution: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

# Lambda-specific main function
async def lambda_main():
    """Adapted version of main() for Lambda execution"""
    logger.info("Initializing ETL components")

    try:
        # Import database modules here to make sure environment variables are set first
        from database import Database
        from feed_fetcher import FeedFetcher
        from article_processor import ArticleProcessor
        from geocoder import Geocoder

        # Initialize database
        logger.info("Initializing database connection")
        db = Database()
        db.initialize_db()
        logger.info("Database connection successful")

        article_queue = asyncio.Queue()

        feed_fetcher = FeedFetcher(db)
        article_processor = ArticleProcessor()
        geocoder = Geocoder()

        await geocoder.initialize()
        logger.info("Geocoder initialized")

        try:
            # Initialize the feed fetcher
            await feed_fetcher.initialize()
            logger.info("Feed fetcher initialized")

            # Instead of continuous polling, fetch once
            logger.info("Fetching RSS feeds")
            new_articles = await feed_fetcher.fetch_all_feeds()
            logger.info(f"Fetched {len(new_articles)} new articles")

            # Queue articles for processing
            for article in new_articles:
                await article_queue.put(article)

            # Create worker tasks
            logger.info("Starting article processing")
            worker_tasks = []
            num_workers = 3
            for i in range(num_workers):
                worker_task = asyncio.create_task(
                    article_processor.process_articles(article_queue, geocoder, db)
                )
                worker_tasks.append(worker_task)

            # Wait for all articles to be processed
            await article_queue.join()
            logger.info("All articles processed")

            # Cancel worker tasks
            for task in worker_tasks:
                task.cancel()

            # Wait for tasks to be cancelled
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error in ETL process: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            logger.info("Cleaning up resources")
            await geocoder.close()
            if hasattr(feed_fetcher, 'session') and feed_fetcher.session:
                await feed_fetcher.close()
    except Exception as e:
        logger.error(f"Error in lambda_main: {e}")
        logger.error(traceback.format_exc())
        raise

# Original main function for local execution
async def main():
    # Import here to ensure environment is set up first when running locally
    from database import Database
    from feed_fetcher import FeedFetcher
    from article_processor import ArticleProcessor
    from geocoder import Geocoder
    from config import POLLING_INTERVAL

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
    logger.info("Starting Mexico News ETL Pipeline locally")
    asyncio.run(main())
