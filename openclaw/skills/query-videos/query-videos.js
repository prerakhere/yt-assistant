#!/usr/bin/env node
/**
 * query-videos skill — searches DynamoDB for YouTube digest data.
 */

const { DynamoDBClient } = require("/app/node_modules/@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient, QueryCommand, ScanCommand } = require("/app/node_modules/@aws-sdk/lib-dynamodb");

const TABLE_NAME = process.env.VIDEOS_TABLE || "yt-digest-videos";
const REGION = process.env.AWS_REGION || "ap-south-1";

const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: REGION }));

async function queryByDate(date) {
  const result = await client.send(new QueryCommand({
    TableName: TABLE_NAME,
    KeyConditionExpression: "#d = :date",
    ExpressionAttributeNames: { "#d": "date" },
    ExpressionAttributeValues: { ":date": date },
  }));
  return result.Items || [];
}

async function queryByChannel(channel, limit = 20) {
  const result = await client.send(new QueryCommand({
    TableName: TABLE_NAME,
    IndexName: "channel-index",
    KeyConditionExpression: "channel = :ch",
    ExpressionAttributeValues: { ":ch": channel },
    Limit: limit,
    ScanIndexForward: false,
  }));
  return result.Items || [];
}

async function searchVideos(keyword, days = 7) {
  const today = new Date();
  const results = [];
  const kw = keyword.toLowerCase();

  for (let i = 0; i < days; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split("T")[0];

    const items = await queryByDate(dateStr);
    for (const item of items) {
      if (
        (item.title && item.title.toLowerCase().includes(kw)) ||
        (item.summary && item.summary.toLowerCase().includes(kw))
      ) {
        results.push(item);
      }
    }
  }
  return results;
}

async function getDigestOrder(date) {
  // Get the ordered digest list
  const orderResult = await client.send(new QueryCommand({
    TableName: TABLE_NAME,
    KeyConditionExpression: "#d = :date AND video_id = :vid",
    ExpressionAttributeNames: { "#d": "date" },
    ExpressionAttributeValues: { ":date": date, ":vid": "digest_order" },
  }));

  const orderItem = (orderResult.Items || [])[0];
  if (!orderItem || !orderItem.ordered_ids) {
    return { error: `No digest found for ${date}` };
  }

  // Get video details for each ID in order
  const videos = await queryByDate(date);
  const videoMap = {};
  for (const v of videos) videoMap[v.video_id] = v;

  return orderItem.ordered_ids.map((id, i) => ({
    position: i + 1,
    video_id: id,
    title: videoMap[id]?.title || "Unknown",
    channel: videoMap[id]?.channel || "Unknown",
  }));
}

// Main: parse command and args
const [, , command, argsJson] = process.argv;
const args = JSON.parse(argsJson || "{}");

(async () => {
  let result;
  switch (command) {
    case "query_videos_by_date":
      result = await queryByDate(args.date);
      break;
    case "query_videos_by_channel":
      result = await queryByChannel(args.channel, args.limit);
      break;
    case "search_videos":
      result = await searchVideos(args.keyword, args.days);
      break;
    case "get_digest_order":
      result = await getDigestOrder(args.date);
      break;
    default:
      result = { error: `Unknown command: ${command}` };
  }
  console.log(JSON.stringify(result, null, 2));
})();
