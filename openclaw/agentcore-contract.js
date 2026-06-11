/**
 * AgentCore contract adapter for OpenClaw.
 * Bridges AgentCore HTTP contract (port 8080) to OpenClaw REST API (port 18789).
 * Binds on 0.0.0.0 — required for AgentCore to reach the container.
 */

const http = require("http");
const fs = require("fs");

const PORT = 8080;
const OPENCLAW_PORT = 18789;

let openclawReady = false;
let gatewayToken = null;

// Read gateway token from config
function loadGatewayToken() {
  try {
    const raw = fs.readFileSync("/root/.openclaw/openclaw.json", "utf8");
    const config = JSON.parse(raw);
    gatewayToken = config.gateway?.auth?.token || null;
    if (gatewayToken) console.log("[contract] Gateway token loaded");
    else console.log("[contract] No gateway token found in config");
  } catch (e) {
    console.log("[contract] Token read error:", e.message);
  }
}

// Poll OpenClaw readiness
function waitForOpenclaw() {
  const check = () => {
    const req = http.get(`http://127.0.0.1:${OPENCLAW_PORT}/healthz`, (res) => {
      if (res.statusCode === 200) {
        openclawReady = true;
        loadGatewayToken();
        console.log("[contract] OpenClaw is ready");
      } else {
        setTimeout(check, 2000);
      }
    });
    req.on("error", () => setTimeout(check, 2000));
    req.end();
  };
  check();
}

// Forward message to OpenClaw REST API
function sendToOpenclaw(message) {
  return new Promise((resolve) => {
    const body = JSON.stringify({
      model: "openclaw",
      messages: [{ role: "user", content: message }],
    });

    const req = http.request({
      hostname: "127.0.0.1",
      port: OPENCLAW_PORT,
      path: "/v1/chat/completions",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${gatewayToken}`,
        "Content-Length": Buffer.byteLength(body),
      },
      timeout: 90000,
    }, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          resolve(parsed.choices?.[0]?.message?.content || data || "(No response)");
        } catch {
          resolve(data || "(Empty response)");
        }
      });
    });

    req.on("error", (err) => resolve(`Error: ${err.message}`));
    req.on("timeout", () => { req.destroy(); resolve("(Timeout)"); });
    req.write(body);
    req.end();
  });
}

const server = http.createServer(async (req, res) => {
  // /ping — always respond Healthy (AgentCore health check)
  if (req.method === "GET" && req.url === "/ping") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "Healthy" }));
    return;
  }

  // /invocations — forward to OpenClaw
  if (req.method === "POST" && req.url === "/invocations") {
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", async () => {
      try {
        const parsed = JSON.parse(body);
        const prompt = parsed.prompt || parsed.input?.prompt || "";

        // Wait up to 60s for OpenClaw to be ready (cold start)
        if (!openclawReady || !gatewayToken) {
          for (let i = 0; i < 30; i++) {
            await new Promise(r => setTimeout(r, 2000));
            if (openclawReady && gatewayToken) break;
          }
        }

        if (!openclawReady || !gatewayToken) {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ response: "OpenClaw failed to start within 60s.", status: "error" }));
          return;
        }

        const response = await sendToOpenclaw(prompt);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ response: response, status: "success" }));
      } catch (err) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ response: `Error: ${err.message}`, status: "error" }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end();
});

// MUST bind to 0.0.0.0 — AgentCore can't reach 127.0.0.1
server.listen(PORT, "0.0.0.0", () => {
  console.log(`[contract] Listening on 0.0.0.0:${PORT}`);
  waitForOpenclaw();
});
