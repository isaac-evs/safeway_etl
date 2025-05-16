provider "aws" {
  region = "us-east-2"
}

# Define environments
locals {
  environment      = "dev" # can be dev, staging, prod
  parameter_prefix = "/mexico-news-etl/${local.environment}"
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_execution_role" {
  name = "mexico_news_etl_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Bedrock access policy
resource "aws_iam_policy" "bedrock_access" {
  name        = "bedrock_access_policy"
  description = "Policy to allow access to AWS Bedrock"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "bedrock:InvokeModel"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

# Attach Bedrock policy to role
resource "aws_iam_role_policy_attachment" "lambda_bedrock_access" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.bedrock_access.arn
}

# SSM Parameter Store access policy
resource "aws_iam_policy" "ssm_parameter_access" {
  name        = "ssm_parameter_access_policy"
  description = "Policy to allow access to SSM Parameter Store"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter${local.parameter_prefix}/*"
      }
    ]
  })
}

# Attach SSM policy to role
resource "aws_iam_role_policy_attachment" "lambda_ssm_access" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.ssm_parameter_access.arn
}

# Create SSM Parameters
resource "aws_ssm_parameter" "aws_access_key_id" {
  name        = "${local.parameter_prefix}/AWS_ACCESS_KEY_ID"
  description = "AWS Access Key ID for Mexico News ETL"
  type        = "SecureString"
  value       = var.aws_access_key_id
}

resource "aws_ssm_parameter" "aws_secret_access_key" {
  name        = "${local.parameter_prefix}/AWS_SECRET_ACCESS_KEY"
  description = "AWS Secret Access Key for Mexico News ETL"
  type        = "SecureString"
  value       = var.aws_secret_access_key
}

resource "aws_ssm_parameter" "aws_region" {
  name        = "${local.parameter_prefix}/AWS_REGION"
  description = "AWS Region for Mexico News ETL"
  type        = "String"
  value       = var.aws_region
}

resource "aws_ssm_parameter" "mapbox_access_token" {
  name        = "${local.parameter_prefix}/MAPBOX_ACCESS_TOKEN"
  description = "Mapbox Access Token for Mexico News ETL"
  type        = "SecureString"
  value       = var.mapbox_access_token
}

resource "aws_ssm_parameter" "claude_model_id" {
  name        = "${local.parameter_prefix}/CLAUDE_MODEL_ID"
  description = "Claude Model ID for Mexico News ETL"
  type        = "String"
  value       = var.claude_model_id
}

resource "aws_ssm_parameter" "db_host" {
  name        = "${local.parameter_prefix}/DB_HOST"
  description = "Database Host for Mexico News ETL"
  type        = "String"
  value       = var.db_host
}

resource "aws_ssm_parameter" "db_port" {
  name        = "${local.parameter_prefix}/DB_PORT"
  description = "Database Port for Mexico News ETL"
  type        = "String"
  value       = var.db_port
}

resource "aws_ssm_parameter" "db_name" {
  name        = "${local.parameter_prefix}/DB_NAME"
  description = "Database Name for Mexico News ETL"
  type        = "String"
  value       = var.db_name
}

resource "aws_ssm_parameter" "db_user" {
  name        = "${local.parameter_prefix}/DB_USER"
  description = "Database User for Mexico News ETL"
  type        = "String"
  value       = var.db_user
}

resource "aws_ssm_parameter" "db_password" {
  name        = "${local.parameter_prefix}/DB_PASSWORD"
  description = "Database Password for Mexico News ETL"
  type        = "SecureString"
  value       = var.db_password
}

resource "aws_ssm_parameter" "polling_interval" {
  name        = "${local.parameter_prefix}/POLLING_INTERVAL"
  description = "Polling Interval for Mexico News ETL"
  type        = "String"
  value       = var.polling_interval
}

resource "aws_ssm_parameter" "max_retries" {
  name        = "${local.parameter_prefix}/MAX_RETRIES"
  description = "Max Retries for Mexico News ETL"
  type        = "String"
  value       = var.max_retries
}

resource "aws_ssm_parameter" "retry_delay" {
  name        = "${local.parameter_prefix}/RETRY_DELAY"
  description = "Retry Delay for Mexico News ETL"
  type        = "String"
  value       = var.retry_delay
}

resource "aws_ssm_parameter" "rss_feeds" {
  name        = "${local.parameter_prefix}/RSS_FEEDS"
  description = "RSS Feeds for Mexico News ETL"
  type        = "String"
  value       = var.rss_feeds
}

# Lambda Function
resource "aws_lambda_function" "mexico_news_etl" {
  function_name = "mexico-news-etl"
  filename      = "mexico_news_etl_lambda.zip"
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "main.lambda_handler"
  runtime       = "python3.9"
  timeout       = 300
  memory_size   = 512

  # Only pass the environment name
  # Remove AWS_REGION as it's a reserved environment variable
  environment {
    variables = {
      ENVIRONMENT = local.environment
      # Do not set AWS_REGION here as it's reserved
    }
  }

  depends_on = [
    aws_ssm_parameter.aws_access_key_id,
    aws_ssm_parameter.aws_secret_access_key,
    aws_ssm_parameter.aws_region,
    aws_ssm_parameter.mapbox_access_token,
    aws_ssm_parameter.claude_model_id,
    aws_ssm_parameter.db_host,
    aws_ssm_parameter.db_port,
    aws_ssm_parameter.db_name,
    aws_ssm_parameter.db_user,
    aws_ssm_parameter.db_password,
    aws_ssm_parameter.polling_interval,
    aws_ssm_parameter.max_retries,
    aws_ssm_parameter.retry_delay,
    aws_ssm_parameter.rss_feeds
  ]
}

# EventBridge rule for scheduling
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "mexico-news-etl-schedule"
  description         = "Trigger Mexico News ETL every 2 hours"
  schedule_expression = "rate(2 hours)"
}

# Target for the event rule
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "mexico-news-etl"
  arn       = aws_lambda_function.mexico_news_etl.arn
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mexico_news_etl.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# Variables
variable "aws_access_key_id" {
  description = "AWS Access Key ID"
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS Secret Access Key"
  sensitive   = true
}

variable "aws_region" {
  description = "AWS Region"
  default     = "us-east-2"
}

variable "mapbox_access_token" {
  description = "Mapbox Access Token"
  sensitive   = true
}

variable "claude_model_id" {
  description = "Claude Model ID"
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "db_host" {
  description = "Database Host"
}

variable "db_port" {
  description = "Database Port"
  default     = 5432
}

variable "db_name" {
  description = "Database Name"
  default     = "news_db"
}

variable "db_user" {
  description = "Database User"
}

variable "db_password" {
  description = "Database Password"
  sensitive   = true
}

variable "polling_interval" {
  description = "Polling Interval in Seconds"
  default     = 7200
}

variable "max_retries" {
  description = "Maximum Retries"
  default     = 3
}

variable "retry_delay" {
  description = "Retry Delay in Seconds"
  default     = 10
}

variable "rss_feeds" {
  description = "RSS Feeds, comma-separated"
  default     = "https://www.mural.com.mx/rss/portada.xml,https://www.elnorte.com/rss/portada.xml,https://www.jornada.com.mx/rss/estados.xml?v=1"
}
