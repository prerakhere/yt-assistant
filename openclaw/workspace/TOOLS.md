# TOOLS.md

## Tool Conventions

- The query-videos skill is at `/skills/query-videos/query-videos.js` (absolute path)
- Run it with: `node /skills/query-videos/query-videos.js <command> '<json_args>'`
- Channel names are case-sensitive — use exact casing as stored (e.g. "Fireship" not "fireship")
- Dates must be in YYYY-MM-DD format
- The script outputs JSON — parse it to present results to the user
