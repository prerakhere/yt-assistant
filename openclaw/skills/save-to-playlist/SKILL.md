# save-to-playlist

Save YouTube videos to a playlist. Default playlist is "Later".

## How to use

```bash
node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["VIDEO_ID_1","VIDEO_ID_2"]}'
```

With a named playlist:
```bash
node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["VIDEO_ID"],"playlist":"AI Videos"}'
```

## Arguments

- `video_ids` (array of strings, required): YouTube video IDs to save
- `playlist` (string, optional): Playlist name. Default: "Later". Case-insensitive match. Creates if not found.

## Output

```json
{"playlist":"Later","playlistCreated":false,"saved":["id1","id2"],"failed":[]}
```
