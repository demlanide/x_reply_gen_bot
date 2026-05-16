import "dotenv/config";
import { Bot, Context, InlineKeyboard, session, SessionFlavor } from "grammy";
import { getLast3Posts, validateUsername, Tweet } from "./twitterClient";
import { generateReplies } from "./replyGenerator";
import { addSub, getUserSubs, loadSubs, markSent, removeSub, wasSent } from "./subscriptions";

interface SessionData {
  waitingForGetPosts: boolean;
  waitingForSub: boolean;
}

type MyContext = Context & SessionFlavor<SessionData>;

const token = process.env.TELEGRAM_BOT_TOKEN;
if (!token) throw new Error("TELEGRAM_BOT_TOKEN is not set");

const bot = new Bot<MyContext>(token);
bot.use(session<SessionData, MyContext>({ initial: () => ({ waitingForGetPosts: false, waitingForSub: false }) }));

function parseUsername(raw: string): string {
  const m = raw.match(/(?:twitter\.com|x\.com)\/([A-Za-z0-9_]+)/);
  if (m) return m[1];
  return raw.trim().replace(/^@/, "");
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatTweetMessage(prefix: string, tweet: Tweet, reply: string): string {
  const preview = tweet.text.length > 200 ? tweet.text.slice(0, 200) + "…" : tweet.text;
  return (
    `<b>${prefix}</b>\n${escapeHtml(preview)}\n\n` +
    `🔗 ${tweet.url}\n\n` +
    `💬 <b>Предлагаемый ответ:</b>\n${escapeHtml(reply)}`
  );
}

async function showSubscriptions(ctx: MyContext, edit = false) {
  const userId = ctx.from!.id;
  const subs = getUserSubs(userId);
  const text = subs.length
    ? `Твои подписки (${subs.length}):\n${subs.map((u) => `• @${u}`).join("\n")}`
    : "У тебя пока нет подписок.";

  const keyboard = new InlineKeyboard().text("➕ Добавить аккаунт", "sub_add");
  for (const u of subs) {
    keyboard.row().text(`❌ Убрать @${u}`, `sub_remove_${u}`);
  }

  const opts = { reply_markup: keyboard, parse_mode: "HTML" as const };
  if (edit) await ctx.editMessageText(text, opts);
  else await ctx.reply(text, opts);
}

async function fetchAndSendPosts(ctx: MyContext, username: string) {
  if (!username) {
    ctx.session.waitingForGetPosts = true;
    await ctx.reply("Не удалось распознать аккаунт. Напиши @username или ссылку на профиль X/Twitter:");
    return;
  }

  const statusMsg = await ctx.reply(`Ищу посты @${username}…`);
  const editStatus = (text: string) =>
    ctx.api.editMessageText(statusMsg.chat.id, statusMsg.message_id, text);

  let unliked: Tweet[], all: Tweet[];
  try {
    ({ unliked, all } = await getLast3Posts(username));
  } catch (e: any) {
    ctx.session.waitingForGetPosts = true;
    await editStatus(
      `Аккаунт @${username} не найден в X/Twitter.\n\nНапиши другой @username или ссылку на профиль:`
    );
    return;
  }

  if (!all.length) {
    await editStatus(`У @${username} нет постов.`);
    return;
  }

  if (!unliked.length) {
    await editStatus(`Все последние ${all.length} поста @${username} уже лайкнуты ✅`);
    return;
  }

  await ctx.api.deleteMessage(statusMsg.chat.id, statusMsg.message_id);

  const replies = await generateReplies(unliked);
  for (let i = 0; i < unliked.length; i++) {
    await ctx.reply(formatTweetMessage(`🐦 Пост @${username}:`, unliked[i], replies[i]), {
      parse_mode: "HTML",
    });
  }
}

// ── Commands ─────────────────────────────────────────────────────────────────

bot.command("start", async (ctx) => {
  await ctx.reply(
    "Привет!\n\n" +
    "/get_posts @username — последние 3 поста (нелайкнутые придут с ответами)\n" +
    "/subscriptions — подписки (проверяю нелайкнутые каждые 2 часа)"
  );
});

bot.command("get_posts", async (ctx) => {
  const arg = ctx.match.trim();
  if (!arg) {
    ctx.session.waitingForGetPosts = true;
    await ctx.reply("Напиши @username или ссылку на профиль X/Twitter:");
    return;
  }
  await fetchAndSendPosts(ctx, parseUsername(arg));
});

bot.command("subscriptions", async (ctx) => {
  await showSubscriptions(ctx);
});

// ── Callback queries ──────────────────────────────────────────────────────────

bot.callbackQuery("sub_add", async (ctx) => {
  await ctx.answerCallbackQuery();
  ctx.session.waitingForSub = true;
  await ctx.reply("Напиши @username или ссылку на аккаунт X/Twitter:");
});

bot.callbackQuery(/^sub_remove_(.+)$/, async (ctx) => {
  await ctx.answerCallbackQuery();
  removeSub(ctx.from.id, ctx.match[1]);
  await showSubscriptions(ctx, true);
});

// ── Text messages ─────────────────────────────────────────────────────────────

bot.on("message:text", async (ctx) => {
  if (ctx.session.waitingForGetPosts) {
    ctx.session.waitingForGetPosts = false;
    await fetchAndSendPosts(ctx, parseUsername(ctx.message.text));
    return;
  }

  if (ctx.session.waitingForSub) {
    ctx.session.waitingForSub = false;
    const username = parseUsername(ctx.message.text);
    if (!username) {
      await ctx.reply("Не удалось распознать имя аккаунта.");
      return;
    }
    if (addSub(ctx.from.id, username)) {
      await ctx.reply(`✅ @${username} добавлен в подписки`);
      await checkOneSubscription(ctx.from.id, username);
    } else {
      await ctx.reply(`@${username} уже в подписках`);
    }
    return;
  }

  await ctx.reply("Используй:\n/get_posts @username — посты\n/subscriptions — подписки");
});

// ── Subscription checks ───────────────────────────────────────────────────────

async function checkOneSubscription(userId: number, username: string) {
  try {
    const { unliked } = await getLast3Posts(username);
    const fresh = unliked.filter((t) => !wasSent(userId, username, t.id));
    if (!fresh.length) return;

    const replies = await generateReplies(fresh);
    for (let i = 0; i < fresh.length; i++) {
      await bot.api.sendMessage(
        userId,
        formatTweetMessage(`🔔 Новый пост @${username}:`, fresh[i], replies[i]),
        { parse_mode: "HTML" }
      );
      markSent(userId, username, fresh[i].id);
    }
  } catch (e) {
    console.error(`Subscription check failed for @${username} / user ${userId}:`, e);
  }
}

async function checkAllSubscriptions() {
  const data = loadSubs();
  for (const [userIdStr, usernames] of Object.entries(data)) {
    for (const username of usernames) {
      await checkOneSubscription(Number(userIdStr), username);
    }
  }
}

// ── Start ─────────────────────────────────────────────────────────────────────

async function main() {
  await bot.api.setMyCommands([
    { command: "get_posts", description: "Последние 3 поста аккаунта X/Twitter" },
    { command: "subscriptions", description: "Управление подписками" },
    { command: "start", description: "Начать работу с ботом" },
  ]);

  const me = await bot.api.getMe();
  console.log(`Бот запущен: @${me.username} (id=${me.id}). Ctrl+C для остановки.`);

  setInterval(async () => {
    console.log("Running subscription check…");
    await checkAllSubscriptions();
  }, 2 * 60 * 60 * 1000);

  await bot.start();
}

main().catch(console.error);
