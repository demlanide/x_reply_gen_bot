import "dotenv/config";
import { TwitterApi } from "twitter-api-v2";

export interface Tweet {
  id: string;
  text: string;
  url: string;
  liked: boolean;
}

function userClient() {
  return new TwitterApi({
    appKey: process.env.TWITTER_API_KEY!,
    appSecret: process.env.TWITTER_API_SECRET!,
    accessToken: process.env.TWITTER_ACCESS_TOKEN!,
    accessSecret: process.env.TWITTER_ACCESS_TOKEN_SECRET!,
  });
}

function appClient() {
  return new TwitterApi(process.env.TWITTER_BEARER_TOKEN!).readOnly;
}

async function getMyUserId(): Promise<string> {
  const me = await userClient().v2.me();
  if (!me.data?.id) throw new Error("Could not get your Twitter user ID");
  return me.data.id;
}

async function getLikedIds(myUserId: string): Promise<Set<string>> {
  const result = await userClient().v2.userLikedTweets(myUserId, { max_results: 100 });
  return new Set((result.data?.data ?? []).map((t) => t.id));
}

export async function validateUsername(username: string): Promise<string> {
  const result = await appClient().v2.userByUsername(username);
  if (!result.data?.id) throw new Error(`NOT_FOUND`);
  return result.data.id;
}

export async function getLast3Posts(username: string): Promise<{ unliked: Tweet[]; all: Tweet[] }> {
  const myUserId = await getMyUserId();
  const targetUserId = await validateUsername(username);
  const likedIds = await getLikedIds(myUserId);

  const timeline = await appClient().v2.userTimeline(targetUserId, {
    max_results: 5,
    exclude: ["retweets", "replies"],
    "tweet.fields": ["id", "text", "created_at"],
  });

  const tweets = (timeline.data?.data ?? []).slice(0, 3);
  const all: Tweet[] = [];
  const unliked: Tweet[] = [];

  for (const tweet of tweets) {
    const t: Tweet = {
      id: tweet.id,
      text: tweet.text,
      url: `https://x.com/${username}/status/${tweet.id}`,
      liked: likedIds.has(tweet.id),
    };
    all.push(t);
    if (!t.liked) unliked.push(t);
  }

  return { unliked, all };
}
