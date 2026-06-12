#!/usr/bin/env node
/**
 * save-to-playlist skill — adds videos to a YouTube playlist.
 *
 * Usage:
 *   node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["id1","id2"]}'
 *   node /skills/save-to-playlist/save-to-playlist.js '{"video_ids":["id1"],"playlist":"AI Videos"}'
 *
 * Default playlist: "Later"
 * If playlist doesn't exist, creates it.
 */

const { SSMClient, GetParameterCommand } = require("/app/node_modules/@aws-sdk/client-ssm");
const https = require("https");

const REGION = process.env.AWS_REGION || "ap-south-1";
const DEFAULT_PLAYLIST = "Later";
const ssm = new SSMClient({ region: REGION });

async function getParam(name) {
  const resp = await ssm.send(new GetParameterCommand({ Name: name, WithDecryption: true }));
  return resp.Parameter.Value;
}

function ytRequest(method, path, accessToken, body) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: "www.googleapis.com",
      path: path,
      method: method,
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    };
    const req = https.request(opts, (res) => {
      let data = "";
      res.on("data", (c) => data += c);
      res.on("end", () => resolve({ status: res.statusCode, data: JSON.parse(data || "{}") }));
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function getAccessToken(refreshToken, clientId, clientSecret) {
  return new Promise((resolve, reject) => {
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
      client_id: clientId,
      client_secret: clientSecret,
    }).toString();
    const req = https.request({
      hostname: "oauth2.googleapis.com",
      path: "/token",
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }, (res) => {
      let data = "";
      res.on("data", (c) => data += c);
      res.on("end", () => {
        const parsed = JSON.parse(data);
        if (parsed.access_token) resolve(parsed.access_token);
        else reject(new Error(parsed.error_description || "Token refresh failed"));
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

async function findOrCreatePlaylist(accessToken, name) {
  // List user's playlists
  const resp = await ytRequest("GET", "/youtube/v3/playlists?part=snippet&mine=true&maxResults=50", accessToken);
  const match = (resp.data.items || []).find(
    (p) => p.snippet.title.toLowerCase() === name.toLowerCase()
  );
  if (match) return { id: match.id, created: false };

  // Create playlist
  const create = await ytRequest("POST", "/youtube/v3/playlists?part=snippet,status", accessToken, {
    snippet: { title: name, description: "Created by YT Assistant" },
    status: { privacyStatus: "private" },
  });
  if (create.status === 200 || create.status === 201) {
    return { id: create.data.id, created: true };
  }
  throw new Error(`Failed to create playlist: ${JSON.stringify(create.data)}`);
}

async function addVideoToPlaylist(accessToken, playlistId, videoId) {
  const resp = await ytRequest("POST", "/youtube/v3/playlistItems?part=snippet", accessToken, {
    snippet: {
      playlistId: playlistId,
      resourceId: { kind: "youtube#video", videoId: videoId },
    },
  });
  if (resp.status === 200 || resp.status === 201) return { success: true, videoId };
  return { success: false, videoId, error: resp.data.error?.message || "Unknown error" };
}

// Main
const args = JSON.parse(process.argv[2] || "{}");
const videoIds = args.video_ids || [];
const playlistName = args.playlist || DEFAULT_PLAYLIST;

if (!videoIds.length) {
  console.log(JSON.stringify({ error: "video_ids array is required" }));
  process.exit(1);
}

(async () => {
  try {
    const [refreshToken, clientId, clientSecret] = await Promise.all([
      getParam("/yt-digest/youtube-refresh-token"),
      getParam("/yt-digest/youtube-client-id"),
      getParam("/yt-digest/youtube-client-secret"),
    ]);

    const accessToken = await getAccessToken(refreshToken, clientId, clientSecret);
    const playlist = await findOrCreatePlaylist(accessToken, playlistName);

    const results = [];
    for (const vid of videoIds) {
      results.push(await addVideoToPlaylist(accessToken, playlist.id, vid));
    }

    const output = {
      playlist: playlistName,
      playlistCreated: playlist.created,
      saved: results.filter(r => r.success).map(r => r.videoId),
      failed: results.filter(r => !r.success).map(r => ({ videoId: r.videoId, error: r.error })),
    };
    console.log(JSON.stringify(output));
  } catch (err) {
    console.log(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
})();
