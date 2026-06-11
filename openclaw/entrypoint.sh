#!/bin/bash
# Entrypoint for OpenClaw on AgentCore Runtime

# Ensure directories are writable
mkdir -p /root/.openclaw/agents/main
mkdir -p /tmp/openclaw

# Disable mDNS and set production mode
export OPENCLAW_DISABLE_BONJOUR=1
export NODE_ENV=production

# Start contract adapter FIRST (responds to /ping immediately)
node /app/agentcore-contract.js &
CONTRACT_PID=$!

# Start OpenClaw gateway (no 'run' subcommand, no daemon fork)
openclaw gateway --port 18789 &
OPENCLAW_PID=$!

# Wait for either process to exit
wait -n $CONTRACT_PID $OPENCLAW_PID
