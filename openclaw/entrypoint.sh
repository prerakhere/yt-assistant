#!/bin/bash
# Entrypoint for OpenClaw on AgentCore Runtime
# Handles persistent storage at /mnt/workspace with smart sync:
# - System files: always overwritten from image (code deploys win)
# - User files: persistent (memory, sessions survive restarts)

MOUNT="/mnt/workspace"
OPENCLAW_DIR="/root/.openclaw"
WORKSPACE="$OPENCLAW_DIR/workspace"

# Disable mDNS and set production mode
export OPENCLAW_DISABLE_BONJOUR=1
export NODE_ENV=production

# Start contract adapter FIRST (responds to /ping immediately)
node /app/agentcore-contract.js &
CONTRACT_PID=$!

# --- Persistent storage setup ---
if [ -d "$MOUNT" ]; then
  echo "[entrypoint] Persistent storage detected at $MOUNT"

  # Create persistent directory structure if first run
  mkdir -p "$MOUNT/.openclaw/workspace/memory"
  mkdir -p "$MOUNT/.openclaw/agents/main/sessions"

  # Copy persistent files FROM mount (memory, sessions — user data)
  # These survive across deploys
  if [ -f "$MOUNT/.openclaw/workspace/MEMORY.md" ]; then
    cp "$MOUNT/.openclaw/workspace/MEMORY.md" "$WORKSPACE/MEMORY.md"
    echo "[entrypoint] Restored MEMORY.md from persistent storage"
  fi
  if [ -d "$MOUNT/.openclaw/workspace/memory" ] && [ "$(ls -A $MOUNT/.openclaw/workspace/memory 2>/dev/null)" ]; then
    cp -r "$MOUNT/.openclaw/workspace/memory/"* "$WORKSPACE/memory/" 2>/dev/null
    echo "[entrypoint] Restored memory/ from persistent storage"
  fi
  if [ -d "$MOUNT/.openclaw/agents" ] && [ "$(ls -A $MOUNT/.openclaw/agents 2>/dev/null)" ]; then
    cp -r "$MOUNT/.openclaw/agents/"* "$OPENCLAW_DIR/agents/" 2>/dev/null
    echo "[entrypoint] Restored agents/ (sessions) from persistent storage"
  fi

  # Do NOT restore SQLite index files — they cause mismatch errors
  # Instead, openclaw memory index --force rebuilds from text files after boot

  # System files are NOT copied from mount — image version always wins
  # (SOUL.md, AGENTS.md, TOOLS.md, IDENTITY.md, USER.md, openclaw.json, skills/)

  # Background job: periodically save user data back to mount
  (
    # Initial sync after OpenClaw starts (give it 15s to boot)
    sleep 15
    cp "$WORKSPACE/MEMORY.md" "$MOUNT/.openclaw/workspace/MEMORY.md" 2>/dev/null
    cp -r "$WORKSPACE/memory/"* "$MOUNT/.openclaw/workspace/memory/" 2>/dev/null
    cp -r "$OPENCLAW_DIR/agents/"* "$MOUNT/.openclaw/agents/" 2>/dev/null
    echo "[sync] Initial sync done"

    while true; do
      sleep 30
      cp "$WORKSPACE/MEMORY.md" "$MOUNT/.openclaw/workspace/MEMORY.md" 2>/dev/null
      cp -r "$WORKSPACE/memory/"* "$MOUNT/.openclaw/workspace/memory/" 2>/dev/null
      cp -r "$OPENCLAW_DIR/agents/"* "$MOUNT/.openclaw/agents/" 2>/dev/null
    done
  ) &
else
  echo "[entrypoint] No persistent storage — ephemeral mode"
fi

# Ensure directories exist
mkdir -p "$WORKSPACE/memory" "$OPENCLAW_DIR/agents/main" /tmp/openclaw

# Start OpenClaw gateway
openclaw gateway --port 18789 &
OPENCLAW_PID=$!

# Rebuild memory index after gateway is fully ready (not just after sleep)
(
  # Wait for OpenClaw health endpoint
  until curl -sf http://127.0.0.1:18789/healthz > /dev/null 2>&1; do
    sleep 2
  done
  sleep 5  # extra buffer for provider auth warmup
  openclaw memory index --force 2>&1 | head -5
  echo "[entrypoint] Memory index rebuilt"
) &

# Wait for any process to exit
wait -n $CONTRACT_PID $OPENCLAW_PID
