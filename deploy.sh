#!/bin/bash

echo "Creating Lambda deployment package with architecture-specific dependencies..."

# Clean up any previous deployment artifacts
rm -rf lambda_deployment
rm -f mexico_news_etl_lambda.zip
rm -rf venv

# Create a directory for the deployment package
mkdir -p lambda_deployment

# Copy all Python files to the deployment directory
cp *.py lambda_deployment/

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install architecture-specific psycopg2-binary for Lambda (x86_64)
echo "Installing architecture-specific psycopg2-binary..."
pip install --platform=manylinux2014_x86_64 --target=lambda_deployment --implementation cp --python-version 3.9 --only-binary=:all: --upgrade psycopg2-binary

# Install other dependencies
echo "Installing other dependencies..."
pip install aiohttp boto3 feedparser python-dotenv greenlet typing_extensions async_timeout --target lambda_deployment/

# List installed packages to verify
echo "Listing installed packages in lambda_deployment:"
ls -la lambda_deployment

# Check if dotenv directory exists
if [ -d "lambda_deployment/dotenv" ]; then
    echo "dotenv directory exists"
else
    echo "dotenv directory does NOT exist. Looking for python-dotenv related files:"
    find lambda_deployment -name "*dotenv*"
fi

# Remove asyncio if it was somehow installed
echo "Cleaning up any standard library packages..."
rm -rf lambda_deployment/asyncio*
rm -rf lambda_deployment/asyncio

# Navigate to the deployment directory and create a ZIP file
cd lambda_deployment
zip -r ../mexico_news_etl_lambda.zip .
cd ..

echo "Deployment package created: mexico_news_etl_lambda.zip"

# Get Lambda function name (modify this if your function has a different name)
FUNCTION_NAME="mexico-news-etl"

# Update Lambda function code directly using AWS CLI
echo "Updating Lambda function code..."
aws lambda update-function-code \
  --function-name $FUNCTION_NAME \
  --zip-file fileb://mexico_news_etl_lambda.zip

echo "Lambda function code updated successfully!"
echo "You can now test your function in the AWS Console."
