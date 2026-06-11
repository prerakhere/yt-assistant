"""CDK stack infrastructure tests."""

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
from stack import YtDigestStack


@pytest.fixture(scope="session")
def template():
    app = cdk.App()
    stack = YtDigestStack(app, "TestStack")
    return Template.from_stack(stack)


def test_lambda_created(template):
    template.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "handler.handler",
        "Runtime": "python3.12",
        "Timeout": 600,
        "MemorySize": 512,
    })


def test_lambda_environment_variables(template):
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": Match.object_like({
                "BEDROCK_REGION": "ap-south-1",
                "BEDROCK_MODEL_PARAM": "/yt-digest/bedrock-model-id",
                "YOUTUBE_TOKEN_PARAM": "/yt-digest/youtube-refresh-token",
                "TELEGRAM_TOKEN_PARAM": "/yt-digest/telegram-bot-token",
                "TELEGRAM_CHAT_ID_PARAM": "/yt-digest/telegram-chat-id",
                "VIDEO_FETCH_MODE_PARAM": "/yt-digest/video-fetch-mode",
            })
        }
    })


def test_eventbridge_rule_schedule(template):
    template.has_resource_properties("AWS::Events::Rule", {
        "ScheduleExpression": "cron(30 0 * * ? *)",
        "State": "ENABLED",
    })


def test_eventbridge_retry_attempts_zero(template):
    template.has_resource_properties("AWS::Events::Rule", {
        "Targets": Match.array_with([
            Match.object_like({
                "RetryPolicy": {"MaximumRetryAttempts": 0}
            })
        ])
    })


def test_dynamodb_table(template):
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "yt-digest-videos",
        "KeySchema": [
            {"AttributeName": "date", "KeyType": "HASH"},
            {"AttributeName": "video_id", "KeyType": "RANGE"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    })


def test_dynamodb_gsi(template):
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "GlobalSecondaryIndexes": Match.array_with([
            Match.object_like({
                "IndexName": "channel-index",
                "KeySchema": [
                    {"AttributeName": "channel", "KeyType": "HASH"},
                    {"AttributeName": "published_at", "KeyType": "RANGE"},
                ],
            })
        ])
    })


def test_ecr_repository(template):
    template.has_resource_properties("AWS::ECR::Repository", {
        "RepositoryName": "yt-assistant-openclaw",
    })


def test_agentcore_role_exists(template):
    template.has_resource_properties("AWS::IAM::Role", {
        "RoleName": "yt-assistant-agentcore-role",
    })


def test_agentcore_role_trust_policy(template):
    template.has_resource_properties("AWS::IAM::Role", {
        "RoleName": "yt-assistant-agentcore-role",
        "AssumeRolePolicyDocument": {
            "Statement": Match.array_with([
                Match.object_like({
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                }),
                Match.object_like({
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock.amazonaws.com"},
                }),
            ])
        }
    })


def test_lambda_has_ssm_permission(template):
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": Match.array_with([
                Match.object_like({
                    "Action": "ssm:GetParameter",
                    "Effect": "Allow",
                })
            ])
        }
    })


def test_lambda_has_bedrock_permission(template):
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": Match.array_with([
                Match.object_like({
                    "Action": "bedrock:InvokeModel",
                    "Effect": "Allow",
                    "Resource": "*",
                })
            ])
        }
    })


def test_router_lambda_created(template):
    template.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "handler.handler",
        "Runtime": "python3.12",
        "Timeout": 120,
        "MemorySize": 256,
    })


def test_router_lambda_environment(template):
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": Match.object_like({
                "AGENT_RUNTIME_ARN": Match.string_like_regexp(".*yt_assistant.*"),
                "TELEGRAM_TOKEN_PARAM": "/yt-digest/telegram-bot-token",
                "TELEGRAM_CHAT_ID_PARAM": "/yt-digest/telegram-chat-id",
            })
        }
    })


def test_router_function_url(template):
    template.has_resource_properties("AWS::Lambda::Url", {
        "AuthType": "NONE",
    })
