import * as fs from "fs";
import * as path from "path";

const SUBS_FILE = path.join(__dirname, "subscriptions.json");
const SENT_FILE = path.join(__dirname, "sent_tweets.json");

function loadJson(file: string): Record<string, any> {
  if (!fs.existsSync(file)) return {};
  return JSON.parse(fs.readFileSync(file, "utf-8"));
}

function saveJson(file: string, data: Record<string, any>) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

export function loadSubs(): Record<string, string[]> {
  return loadJson(SUBS_FILE);
}

export function getUserSubs(userId: number): string[] {
  return loadSubs()[String(userId)] ?? [];
}

export function addSub(userId: number, username: string): boolean {
  const data = loadSubs();
  const key = String(userId);
  const subs = data[key] ?? [];
  if (subs.some((u: string) => u.toLowerCase() === username.toLowerCase())) return false;
  data[key] = [...subs, username];
  saveJson(SUBS_FILE, data);
  return true;
}

export function removeSub(userId: number, username: string): boolean {
  const data = loadSubs();
  const key = String(userId);
  const before: string[] = data[key] ?? [];
  const after = before.filter((u) => u.toLowerCase() !== username.toLowerCase());
  if (before.length === after.length) return false;
  data[key] = after;
  saveJson(SUBS_FILE, data);
  return true;
}

export function wasSent(userId: number, username: string, tweetId: string): boolean {
  const data = loadJson(SENT_FILE);
  return (data[String(userId)]?.[username.toLowerCase()] ?? []).includes(tweetId);
}

export function markSent(userId: number, username: string, tweetId: string) {
  const data = loadJson(SENT_FILE);
  const key = String(userId);
  const uname = username.toLowerCase();
  if (!data[key]) data[key] = {};
  if (!data[key][uname]) data[key][uname] = [];
  if (!data[key][uname].includes(tweetId)) data[key][uname].push(tweetId);
  saveJson(SENT_FILE, data);
}
