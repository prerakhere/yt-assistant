"""HTTP server implementing AgentCore contract (port 8080, /ping, /invocations).

Uses BedrockAgentCoreApp SDK which auto-handles /ping and /invocations routing.
Each invocation creates a fresh agent with memory loaded from AgentCore Memory.
"""

import os
import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent import create_agent, _today_ist

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

SESSION_ID = os.environ.get("RUNTIME_SESSION_ID", "yt_assistant_session")


@app.entrypoint
def invoke(payload):
    """Process incoming request from AgentCore runtime."""
    logger.info(f"Received payload keys: {list(payload.keys())}")
    prompt = payload.get("prompt", "")
    if not prompt:
        return {"response": "No prompt provided.", "status": "error"}

    try:
        agent = create_agent(session_id=SESSION_ID)
        result = agent(prompt)

        # Flush memory after each invocation
        if hasattr(agent, 'session_manager') and agent.session_manager:
            try:
                agent.session_manager.close()
                logger.info("[memory] Flushed conversation to AgentCore Memory")
            except Exception as e:
                logger.error(f"[memory] FLUSH FAILED: {type(e).__name__}: {e}")

        # Extract text from agent result
        if result.message and result.message.get("content"):
            parts = []
            for block in result.message["content"]:
                if "text" in block:
                    parts.append(block["text"])
            response_text = "\n".join(parts) if parts else "(No response)"
        else:
            response_text = "(No response)"
        return {"response": response_text, "status": "success"}
    except Exception as e:
        logger.exception("Agent invocation failed")
        return {"response": f"Error: {e}", "status": "error"}


if __name__ == "__main__":
    app.run()
