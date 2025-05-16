import asyncio
import logging
import sys
import json
import boto3
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# This handler will be triggered first to just log all environment variables and parameters
def lambda_handler(event, context):
    logger.info("Starting Mexico News ETL Pipeline in Lambda - DEBUG MODE")

    try:
        # Log the environment variables
        logger.info("Environment variables:")
        for key, value in os.environ.items():
            # Don't log the actual values of sensitive environment variables
            if key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'DB_PASSWORD', 'MAPBOX_ACCESS_TOKEN']:
                logger.info(f"{key}: [REDACTED]")
            else:
                logger.info(f"{key}: {value}")

        # Log the ENVIRONMENT variable specifically
        env_var = os.environ.get('ENVIRONMENT')
        logger.info(f"ENVIRONMENT variable: {env_var}")

        # Try to get parameters from SSM
        logger.info("Attempting to get parameters from SSM...")
        params = get_parameters()

        # Log the parameters (redacting sensitive values)
        logger.info("Parameters retrieved from SSM:")
        for key, value in params.items():
            if key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'DB_PASSWORD', 'MAPBOX_ACCESS_TOKEN']:
                logger.info(f"{key}: [REDACTED]")
            else:
                logger.info(f"{key}: {value}")

        # Log the database configuration that would be used
        db_host = params.get('DB_HOST', os.environ.get('DB_HOST', 'localhost'))
        db_port = params.get('DB_PORT', os.environ.get('DB_PORT', '5432'))
        db_name = params.get('DB_NAME', os.environ.get('DB_NAME', 'news_db'))
        db_user = params.get('DB_USER', os.environ.get('DB_USER', 'postgres'))
        logger.info(f"Database connection would use: host={db_host}, port={db_port}, dbname={db_name}, user={db_user}")

        return {
            'statusCode': 200,
            'body': json.dumps('Debug information logged to CloudWatch')
        }
    except Exception as e:
        logger.error(f"Error in Lambda debug handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error in debug mode: {str(e)}')
        }

# Function to get parameters from SSM Parameter Store
def get_parameters():
    """
    Retrieve parameters from AWS Systems Manager Parameter Store
    """
    try:
        # Get the environment (dev, stage, prod)
        env = os.environ.get('ENVIRONMENT', 'dev')

        # Use the AWS region from Lambda's environment
        region = os.environ.get('AWS_REGION', 'us-east-2')

        # Path prefix for our parameters
        path = f"/mexico-news-etl/{env}/"

        logger.info(f"Getting parameters from {path} in region {region}")

        # Initialize SSM client with the region
        ssm = boto3.client('ssm', region_name=region)

        # Get all parameters by path with decryption
        try:
            response = ssm.get_parameters_by_path(
                Path=path,
                Recursive=True,
                WithDecryption=True
            )

            # Log raw response for debugging (excluding actual parameter values)
            params_count = len(response.get('Parameters', []))
            logger.info(f"SSM response received with {params_count} parameters")

            if params_count == 0:
                logger.warning(f"No parameters found at path: {path}")
                logger.info("Trying to list all parameter paths for troubleshooting...")
                try:
                    # This will help identify if parameters exist but at a different path
                    all_params = ssm.describe_parameters()
                    param_names = [p.get('Name') for p in all_params.get('Parameters', [])]
                    logger.info(f"Available parameters: {param_names}")
                except Exception as e:
                    logger.warning(f"Could not list parameters: {e}")

        except Exception as e:
            logger.error(f"Error calling SSM: {e}")
            return {}

        # Create a dictionary of parameters
        parameters = {}
        for param in response.get('Parameters', []):
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

            for param in response.get('Parameters', []):
                name = param['Name'].replace(path, '')
                parameters[name] = param['Value']

        logger.info(f"Retrieved {len(parameters)} parameters from SSM Parameter Store")

        # Make sure we set AWS_REGION in the parameters
        if 'AWS_REGION' not in parameters:
            parameters['AWS_REGION'] = region

        return parameters

    except Exception as e:
        logger.error(f"Error retrieving parameters: {e}")
        logger.exception("Full stack trace:")
        # Return an
