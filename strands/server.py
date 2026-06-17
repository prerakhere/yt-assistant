"""HTTP server implementing AgentCore contract (port 8080, /ping, /invocations).

Uses BedrockAgentCoreApp SDK which auto-handles /ping and /invocations routing.
The runtimeSessionId is passed by AgentCore via the X-Amzn-Bedrock-AgentCore-Runtime-Session-Id header.
Since each session gets its own microVM, we keep a single agent instance per container.
"""

import os
import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent import create_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# Single agent instance per microVM (one session = one microVM in AgentCore)
SESSION_ID = os.environ.get("RUNTIME_SESSION_ID", "yt_assistant_session")
agent = None
agent_date = None


def get_agent():
    global agent, agent_date
    from agent import _today_ist
    today = _today_ist()
    if agent is None or agent_date != today:
        agent = create_agent(session_id=SESSION_ID)
        agent_date = today
    return agent


@app.entrypoint
def invoke(payload):
    """Process incoming request from AgentCore runtime."""
    logger.info(f"Received payload: {payload}")
    prompt = payload.get("prompt", "")
    if not prompt:
        return {"response": "No prompt provided.", "status": "error"}

    try:
        a = get_agent()
        result = a(prompt)
        logger.info(f"Agent result message: {result.message}")
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
