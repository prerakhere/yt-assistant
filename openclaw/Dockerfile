# Minimal OpenClaw on AgentCore Runtime
FROM --platform=linux/arm64 public.ecr.aws/docker/library/node:22-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl jq git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Force git to use HTTPS instead of SSH
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"

# Install OpenClaw
RUN npm install -g openclaw@latest

# App directory with AWS SDK for DynamoDB skill
RUN mkdir -p /app && cd /app && npm init -y > /dev/null 2>&1 && \
    npm install --omit=dev @aws-sdk/client-dynamodb @aws-sdk/lib-dynamodb ws

ENV NODE_PATH=/app/node_modules
WORKDIR /app

# Pre-create OpenClaw config and copy config first
RUN mkdir -p /root/.openclaw
COPY openclaw.json /root/.openclaw/openclaw.json

# Install amazon-bedrock provider plugin AFTER config exists
RUN echo y | openclaw plugins install npm:@openclaw/amazon-bedrock-provider

# Copy remaining files
COPY agentcore-contract.js /app/agentcore-contract.js
COPY test-contract.js /app/test-contract.js
COPY workspace/SOUL.md /root/.openclaw/SOUL.md
COPY workspace/USER.md /root/.openclaw/USER.md
COPY workspace/AGENTS.md /root/.openclaw/AGENTS.md
COPY skills/ /skills/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh /skills/query-videos/query-videos.js

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
