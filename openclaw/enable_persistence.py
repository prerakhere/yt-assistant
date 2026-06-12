"""Update AgentCore Runtime to enable session storage."""

import boto3

client = boto3.client("bedrock-agentcore-control", region_name="ap-south-1")

response = client.update_agent_runtime(
    agentRuntimeId="yt_assistant-Qpf0juCKa5",
    agentRuntimeArtifact={
        "containerConfiguration": {
            "containerUri": "597574415250.dkr.ecr.ap-south-1.amazonaws.com/yt-assistant-openclaw:latest"
        }
    },
    networkConfiguration={"networkMode": "PUBLIC"},
    roleArn="arn:aws:iam::597574415250:role/yt-assistant-agentcore-role",
    environmentVariables={
        "AWS_REGION": "ap-south-1",
        "VIDEOS_TABLE": "yt-digest-videos",
    },
    filesystemConfigurations=[
        {
            "sessionStorage": {
                "mountPath": "/mnt/workspace"
            }
        }
    ],
)

print(f"Updated! Status: {response['status']}")
