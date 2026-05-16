import "dotenv/config";
import OpenAI from "openai";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function generateReply(tweetText: string): Promise<string> {
  const response = await client.chat.completions.create({
    model: "gpt-4o",
    max_tokens: 256,
    messages: [
      {
        role: "system",
        content:
          "You help write short, genuine, engaging replies to tweets. " +
          "Always reply in the same language as the tweet. " +
          "Write in first person, no hashtags, no emoji unless the original has them. " +
          "One or two sentences maximum.",
      },
      {
        role: "user",
        content: `Write a reply to this tweet:\n\n${tweetText}`,
      },
    ],
  });
  return response.choices[0].message.content?.trim() ?? "";
}

export async function generateReplies(tweets: { text: string }[]): Promise<string[]> {
  return Promise.all(tweets.map((t) => generateReply(t.text)));
}
