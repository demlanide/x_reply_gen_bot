import asyncio
import logging
import os
import re

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from reply_generator import generate_replies
from subscriptions import (
    add_sub,
    get_user_subs,
    load_subs,
    mark_sent,
    remove_sub,
    was_sent,
)
from twitter_client import get_last_3_posts

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def parse_username(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", raw)
    if m:
        return m.group(1)
    return raw.lstrip("@")


def _format_tweet_message(prefix: str, username: str, tweet: dict, reply: str) -> str:
    preview = tweet["text"][:200] + ("…" if len(tweet["text"]) > 200 else "")
    return (
        f"{prefix}\n{preview}\n\n"
        f"🔗 {tweet['url']}\n\n"
        f"💬 *Предлагаемый ответ:*\n{reply}"
    )


async def _show_subscriptions(target, user_id: int, edit: bool = False):
    subs = get_user_subs(user_id)
    text = (
        f"Твои подписки ({len(subs)}):\n" + "\n".join(f"• @{u}" for u in subs)
        if subs
        else "У тебя пока нет подписок."
    )
    keyboard = [[InlineKeyboardButton("➕ Добавить аккаунт", callback_data="sub_add")]]
    for u in subs:
        keyboard.append([InlineKeyboardButton(f"❌ Убрать @{u}", callback_data=f"sub_remove_{u}")])
    markup = InlineKeyboardMarkup(keyboard)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.message.reply_text(text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет!\n\n"
        "/getPosts @username — последние 3 поста (нелайкнутые придут с ответами)\n"
        "/subscriptions — подписки (проверяю нелайкнутые каждые 2 часа)"
    )


async def _fetch_and_send_posts(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str):
    """Fetch last 3 posts for username and send results. Sets waiting_for_getposts if profile not found."""
    if not username:
        context.user_data["waiting_for_getposts"] = True
        await update.message.reply_text(
            "Не удалось распознать аккаунт. Напиши @username или ссылку на профиль X/Twitter:"
        )
        return

    status = await update.message.reply_text(f"Ищу посты @{username}…")
    try:
        unliked, all_tweets = get_last_3_posts(username)
    except ValueError as e:
        context.user_data["waiting_for_getposts"] = True
        await status.edit_text(
            f"Аккаунт @{username} не найден в X/Twitter.\n\nНапиши другой @username или ссылку на профиль:"
        )
        return
    except Exception as e:
        await status.edit_text(f"Ошибка при получении твитов: {e}")
        return

    if not all_tweets:
        await status.edit_text(f"У @{username} нет постов.")
        return

    if not unliked:
        await status.edit_text(f"Все последние {len(all_tweets)} поста @{username} уже лайкнуты ✅")
        return

    await status.delete()
    try:
        replies = generate_replies(unliked)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при генерации ответов: {e}")
        return

    for tweet, reply in zip(unliked, replies):
        await update.message.reply_text(
            _format_tweet_message(f"🐦 *Пост @{username}:*", username, tweet, reply),
            parse_mode="Markdown",
        )


async def get_posts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        context.user_data["waiting_for_getposts"] = True
        await update.message.reply_text(
            "Напиши @username или ссылку на профиль X/Twitter:"
        )
        return

    username = parse_username(context.args[0])
    await _fetch_and_send_posts(update, context, username)


async def subscriptions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_subscriptions(update, update.effective_user.id)


async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "sub_add":
        context.user_data["waiting_for_sub"] = True
        await query.message.reply_text(
            "Напиши @username или ссылку на аккаунт X/Twitter:"
        )
    elif query.data.startswith("sub_remove_"):
        username = query.data[len("sub_remove_"):]
        remove_sub(user_id, username)
        await _show_subscriptions(query, user_id, edit=True)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_getposts"):
        context.user_data["waiting_for_getposts"] = False
        username = parse_username(update.message.text)
        await _fetch_and_send_posts(update, context, username)
        return

    if context.user_data.get("waiting_for_sub"):
        context.user_data["waiting_for_sub"] = False
        username = parse_username(update.message.text)
        if not username:
            await update.message.reply_text("Не удалось распознать имя аккаунта.")
            return
        if add_sub(update.effective_user.id, username):
            await update.message.reply_text(f"✅ @{username} добавлен в подписки")
            await _check_one_subscription(update.effective_user.id, username, context.bot)
        else:
            await update.message.reply_text(f"@{username} уже в подписках")
        return

    await update.message.reply_text(
        "Используй:\n/getPosts @username — посты\n/subscriptions — подписки"
    )


async def _check_one_subscription(user_id: int, username: str, bot):
    try:
        unliked, _ = get_last_3_posts(username)
        new_unliked = [t for t in unliked if not was_sent(user_id, username, t["id"])]
        if not new_unliked:
            return
        replies = generate_replies(new_unliked)
        for tweet, reply in zip(new_unliked, replies):
            await bot.send_message(
                user_id,
                _format_tweet_message(f"🔔 *Новый пост @{username}:*", username, tweet, reply),
                parse_mode="Markdown",
            )
            mark_sent(user_id, username, tweet["id"])
    except Exception as e:
        logging.error(f"Subscription check failed for @{username} / user {user_id}: {e}")


async def _check_subscriptions(app: Application):
    data = load_subs()
    for user_id_str, usernames in data.items():
        user_id = int(user_id_str)
        for username in usernames:
            await _check_one_subscription(user_id, username, app.bot)


async def _subscription_loop(app: Application):
    while True:
        await asyncio.sleep(2 * 3600)
        logging.info("Running subscription check…")
        await _check_subscriptions(app)


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getPosts", get_posts_cmd))
    app.add_handler(CommandHandler("subscriptions", subscriptions_cmd))
    app.add_handler(CallbackQueryHandler(subscription_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    me = await app.bot.get_me()
    print(f"Бот запущен: @{me.username} (id={me.id}). Ctrl+C для остановки.")

    async with app:
        await app.bot.delete_webhook(drop_pending_updates=False)
        await app.start()
        asyncio.create_task(_subscription_loop(app))
        await app.updater.start_polling()
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
