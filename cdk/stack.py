"""
CDK Stack — defines all AWS infrastructure for the YouTube digest.

Resources created:
- Lambda function (runs the digest logic)
- EventBridge Schedule (triggers Lambda daily at 8:00 AM IST)
- IAM permissions (Bedrock invoke, SSM read)
"""

from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class YtDigestStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # SSM parameter names (you'll create these manually during setup)
        youtube_param = "/yt-digest/youtube-refresh-token"
        telegram_token_param = "/yt-digest/telegram-bot-token"
        telegram_chat_id_param = "/yt-digest/telegram-chat-id"

        # SSM params for YouTube OAuth app credentials
        youtube_client_id_param = "/yt-digest/youtube-client-id"
        youtube_client_secret_param = "/yt-digest/youtube-client-secret"
        bedrock_model_param = "/yt-digest/bedrock-model-id"

        # DynamoDB table for storing video digests
        table = dynamodb.Table(
            self,
            "VideosTable",
            table_name="yt-digest-videos",
            partition_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="video_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # GSI to query by channel
        table.add_global_secondary_index(
            index_name="channel-index",
            partition_key=dynamodb.Attribute(name="channel", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="published_at", type=dynamodb.AttributeType.STRING),
        )

        # Lambda function with bundled dependencies
        fn = _lambda.Function(
            self,
            "DigestFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(
                "../lambda",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.minutes(10),
            memory_size=512,
            environment={
                "BEDROCK_REGION": "ap-south-1",
                "BEDROCK_MODEL_PARAM": bedrock_model_param,
                "YOUTUBE_TOKEN_PARAM": youtube_param,
                "YOUTUBE_CLIENT_ID_PARAM": youtube_client_id_param,
                "YOUTUBE_CLIENT_SECRET_PARAM": youtube_client_secret_param,
                "TELEGRAM_TOKEN_PARAM": telegram_token_param,
                "TELEGRAM_CHAT_ID_PARAM": telegram_chat_id_param,
                "VIDEOS_TABLE": table.table_name,
            },
        )

        # Permission: read SSM parameters
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/yt-digest/*"
                ],
            )
        )

        # Permission: invoke Bedrock model (any model/region — cross-region profiles route dynamically)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # Permission: write to DynamoDB
        table.grant_write_data(fn)

        # EventBridge rule: daily at 6:00 AM IST (= 0:30 AM UTC)
        rule = events.Rule(
            self,
            "DailyTrigger",
            schedule=events.Schedule.cron(hour="0", minute="30"),
        )
        rule.add_target(targets.LambdaFunction(fn, retry_attempts=0))
