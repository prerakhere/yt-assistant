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
    CfnOutput,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
    aws_ecr as ecr,
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
                "VIDEO_FETCH_MODE_PARAM": "/yt-digest/video-fetch-mode",
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

        # --- OpenClaw on AgentCore ---

        # ECR repository for OpenClaw container image
        ecr_repo = ecr.Repository(
            self,
            "OpenClawRepo",
            repository_name="yt-assistant-openclaw",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # AgentCore execution role (assumed by the AgentCore container)
        agentcore_role = iam.Role(
            self,
            "AgentCoreRole",
            role_name="yt-assistant-agentcore-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
                iam.ServicePrincipal("bedrock.amazonaws.com"),
            ),
        )

        # AgentCore needs: Bedrock invoke, DynamoDB read, SSM read, ECR pull
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                         "bedrock:Converse", "bedrock:ConverseStream"],
                resources=["*"],
            )
        )
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"],
                resources=["*"],
            )
        )
        table.grant_read_data(agentcore_role)
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/yt-digest/*"
                ],
            )
        )
        ecr_repo.grant_pull(agentcore_role)

        # Outputs
        CfnOutput(self, "EcrRepoUri", value=ecr_repo.repository_uri)
        CfnOutput(self, "AgentCoreRoleArn", value=agentcore_role.role_arn)

        # --- Router Lambda (Telegram webhook → AgentCore) ---

        router_fn = _lambda.Function(
            self,
            "RouterFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(
                "../router",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.seconds(120),
            memory_size=256,
            environment={
                "AGENT_RUNTIME_ARN": "arn:aws:bedrock-agentcore:ap-south-1:597574415250:runtime/yt_assistant-Qpf0juCKa5",
                "TELEGRAM_TOKEN_PARAM": telegram_token_param,
                "TELEGRAM_CHAT_ID_PARAM": telegram_chat_id_param,
                "TELEGRAM_WEBHOOK_SECRET": "yt-assist-webhook-secret-2026",
            },
        )

        # Router needs: SSM read, AgentCore invoke
        router_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/yt-digest/*"
                ],
            )
        )
        router_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"],
            )
        )

        # Function URL (public HTTPS endpoint for Telegram webhook)
        fn_url = router_fn.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        # Grant public invoke (required since Oct 2025 for NONE auth)
        router_fn.grant_invoke_url(iam.AnyPrincipal())

        # Also need lambda:InvokeFunction for public Function URLs (Oct 2025 requirement)
        _lambda.CfnPermission(
            self,
            "RouterFnPublicInvoke",
            action="lambda:InvokeFunction",
            function_name=router_fn.function_name,
            principal="*",
        )

        CfnOutput(self, "RouterFunctionUrl", value=fn_url.url)
