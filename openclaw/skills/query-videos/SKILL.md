# query-videos

Query YouTube subscription video digests from DynamoDB.

## How to use

Run the script with node. The script is at `/skills/query-videos/query-videos.js`.

### Get videos by date

```bash
node /skills/query-videos/query-videos.js query_videos_by_date '{"date":"2026-06-10"}'
```

### Get videos by channel

```bash
node /skills/query-videos/query-videos.js query_videos_by_channel '{"channel":"Fireship"}'
```

### Search by keyword

```bash
node /skills/query-videos/query-videos.js search_videos '{"keyword":"kubernetes","days":7}'
```

## Output

Returns JSON array of videos with: title, channel, summary, date, video_id.

### Get digest order (numbered list from morning digest)

```bash
node /skills/query-videos/query-videos.js get_digest_order '{"date":"2026-06-12"}'
```

Returns ordered list with position numbers matching the morning Telegram digest. Use this when user says "save 2 5 7" referring to the daily digest.
