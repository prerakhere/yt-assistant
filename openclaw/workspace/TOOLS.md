# TOOLS.md

## Tool Conventions

### query-videos
- Script: `/skills/query-videos/query-videos.js` (absolute path)
- Run: `node /skills/query-videos/query-videos.js <command> '<json_args>'`
- Channel names are case-sensitive — use exact casing as stored (e.g. "Fireship" not "fireship")
- Dates must be in YYYY-MM-DD format
- Output: JSON array

### save-to-playlist
- Script: `/skills/save-to-playlist/save-to-playlist.js` (absolute path)
- Run: `node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["ID1","ID2"]}'`
- With named playlist: `node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["ID1"],"playlist":"AI Videos"}'`
- Default playlist: "Later"
- Output: JSON with saved/failed lists
