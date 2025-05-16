#!/bin/bash

echo "Fixing SSM Parameter Store permissions for Lambda role..."

# Get the Lambda function name and role
FUNCTION_NAME="mexico-news-etl"
ROLE_ARN=$(aws lambda get-function --function-name "$FUNCTION_NAME" --query "Configuration.Role" --output text)

if [ -z "$ROLE_ARN" ]; then
    echo "❌ Could not get the IAM role for Lambda function $FUNCTION_NAME"
    exit 1
fi

echo "Lambda role ARN: $ROLE_ARN"
ROLE_NAME=$(echo "$ROLE_ARN" | sed 's/.*\/\(.*\)/\1/')
echo "Role name: $ROLE_NAME"

# Create a more comprehensive SSM policy
echo "Creating updated SSM parameter access policy..."

# Create policy document with broader permissions
cat > ssm_policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath",
                "ssm:DescribeParameters"
            ],
            "Resource": "*"
        }
    ]
}
EOF

# Check if policy already exists
POLICY_NAME="ssm_parameter_access_policy_full"
EXISTING_POLICY=$(aws iam list-policies --query "Policies[?PolicyName=='$POLICY_NAME'].Arn" --output text)

if [ -n "$EXISTING_POLICY" ]; then
    echo "Policy already exists: $EXISTING_POLICY"
    POLICY_ARN=$EXISTING_POLICY
else
    # Create the policy
    POLICY_ARN=$(aws iam create-policy --policy-name $POLICY_NAME --policy-document file://ssm_policy.json --query "Policy.Arn" --output text)

    if [ $? -ne 0 ]; then
        echo "❌ Failed to create policy"
        exit 1
    fi

    echo "✅ Created policy: $POLICY_ARN"
fi

# Attach the policy to the role
echo "Attaching policy to Lambda role..."
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$POLICY_ARN"

if [ $? -eq 0 ]; then
    echo "✅ Attached policy to role successfully"
else
    echo "❌ Failed to attach policy to role"
    exit 1
fi

# Clean up
rm ssm_policy.json

echo ""
echo "Creating required SSM parameters..."

# Set environment and region
ENV=${ENVIRONMENT:-dev}
REGION=${AWS_REGION:-us-east-2}
PATH_PREFIX="/mexico-news-etl/$ENV"

echo "Environment: $ENV"
echo "Region: $REGION"
echo "Path prefix: $PATH_PREFIX"

# Required parameters to create
PARAMS=(
    "DB_HOST:Your database hostname"
    "DB_PORT:5432"
    "DB_NAME:news_db"
    "DB_USER:Your database username"
    "DB_PASSWORD:Your database password:SecureString"
    "AWS_ACCESS_KEY_ID:Your AWS access key:SecureString"
    "AWS_SECRET_ACCESS_KEY:Your AWS secret key:SecureString"
    "AWS_REGION:$REGION"
    "MAPBOX_ACCESS_TOKEN:Your Mapbox access token:SecureString"
    "CLAUDE_MODEL_ID:us.anthropic.claude-3-5-haiku-20241022-v1:0"
    "POLLING_INTERVAL:7200"
    "MAX_RETRIES:3"
    "RETRY_DELAY:10"
    "RSS_FEEDS:https://www.mural.com.mx/rss/portada.xml,https://www.elnorte.com/rss/portada.xml,https://www.jornada.com.mx/rss/estados.xml?v=1"
)

# Create or update required parameters
for param_info in "${PARAMS[@]}"; do
    # Parse the parameter info (name:default_value:type)
    IFS=':' read -r name default_value param_type <<< "$param_info"

    # Default to String type if not specified
    if [ -z "$param_type" ]; then
        param_type="String"
    fi

    # Parameter path with and without leading slash
    PARAM_PATH="$PATH_PREFIX/$name"
    PARAM_PATH_NO_SLASH="mexico-news-etl/$ENV/$name"

    # Prompt for the value if it's a sensitive parameter
    if [[ "$param_type" == "SecureString" || "$default_value" == *"Your"* ]]; then
        read -p "Enter value for $name: " value
        if [ -z "$value" ]; then
            value="$default_value"
            echo "Using default value (this won't work for actual credentials)"
        fi
    else
        value="$default_value"
    fi

    # Create the parameter (try both paths)
    echo "Creating parameter $PARAM_PATH..."
    aws ssm put-parameter --name "$PARAM_PATH" --value "$value" --type "$param_type" --overwrite

    if [ $? -eq 0 ]; then
        echo "✅ Created/updated parameter $PARAM_PATH"
    else
        echo "Failed to create parameter with leading slash. Trying without leading slash..."
        aws ssm put-parameter --name "$PARAM_PATH_NO_SLASH" --value "$value" --type "$param_type" --overwrite

        if [ $? -eq 0 ]; then
            echo "✅ Created/updated parameter $PARAM_PATH_NO_SLASH"
        else
            echo "❌ Failed to create parameter with either path format"
        fi
    fi
done

echo ""
echo "Permissions and parameters setup complete."
echo "Now re-deploy the Lambda function to apply changes:"
echo "1. Wait a few minutes for IAM permissions to propagate"
echo "2. Run your deployment script to update the Lambda function"
echo "3. Test the Lambda function again"
