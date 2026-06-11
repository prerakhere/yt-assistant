# query-videos

Search your YouTube subscription digest history stored in DynamoDB.

## Tools

### query_videos_by_date

Query videos from a specific date.

**Arguments:**
- `date` (string, required): Date in YYYY-MM-DD format

**Example:** `query_videos_by_date("2026-06-10")`

### query_videos_by_channel

Query all videos from a specific channel.

**Arguments:**
- `channel` (string, required): Channel name (exact match)
- `limit` (number, optional): Max results (default: 20)

**Example:** `query_videos_by_channel("Fireship")`

### search_videos

Search videos by keyword in title or summary across recent days.

**Arguments:**
- `keyword` (string, required): Search term
- `days` (number, optional): How many days back to search (default: 7)

**Example:** `search_videos("kubernetes", 14)`
