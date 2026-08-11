"""Telegram News Bot (aiogram v3 + stdlib RSS/Atom парсер + apscheduler).

Стек: aiogram v3 (Telegram Bot API) + httpx (загрузка лент) +
xml.etree из стандартной библиотеки (парсинг RSS 2.0 / Atom) +
aiosqlite (дедупликация новостей, подписки) + APScheduler (ежедневный дайджест).

Команды:
  /news [URL]       — свежие новости (по умолчанию Lenta.ru)
  /sources          — встроенные ленты (бесплатные, без ключа)
  /digest on|off    — ежедневный дайджест подписанных лент (в 9:00)
  /mysubs           — на какие ленты включён дайджест
  /latest           — последние сохранённые новости из БД
  /stats            — сколько новостей уже обработано

Продвинутый уровень:
  - единый парсер RSS и Atom на stdlib (кодировка из байтов, html.unescape);
  - дедупликация по UNIQUE(link) — одна новость никогда не придёт дважды;
  - TTL-кэш лент + retry с джиттером; middlewares: троттлинг и логирование.

Запуск:  python bot.py   (задайте NEWS_BOT_TOKEN, или run_bot9.cmd).
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from db import Database
from middlewares import LoggingMiddleware, ThrottlingMiddleware
from rss_parser import FeedFetcher
from utils import TTLCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.BASE_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

router = Router()
db = Database()
fetcher = FeedFetcher()
feed_cache = TTLCache(ttl_seconds=config.CACHE_TTL_SECONDS)

_bot: Bot | None = None
scheduler = AsyncIOScheduler()


def _format_news(items: list, header: str = "") -> str:
    lines = [f"📰 <b>{_html.escape(header)}</b>"] if header else []
    for it in items:
        date_part = f" · <i>{_html.escape(it.published)}</i>" if it.published else ""
        lines.append(
            f"• <a href=\"{_html.escape(it.link)}\">{_html.escape(it.title)}</a>{date_part}"
        )
    return "\n".join(lines) if lines else "Новостей пока нет."


# ---------------------------------------------------------------- команды

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "📰 <b>Telegram News Bot</b>\n\n"
        "/news — свежие новости (Lenta.ru)\n"
        "/news https://…/rss.xml — своя RSS/Atom лента\n"
        "/sources — встроенные ленты\n"
        "/digest on — ежедневный дайджест (в 9:00)\n"
        "/mysubs — мои подписки на дайджест\n"
        "/latest — последние сохранённые\n\n"
        f"Источник: <b>{'демо-данные' if fetcher.demo_mode else 'RSS/Atom-ленты'}</b>"
    )


@router.message(Command("news"))
async def cmd_news(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    url = (args[1] if len(args) > 1 else config.DEFAULT_FEED_URL).strip()
    source = next((f["name"] for f in config.DEFAULT_FEEDS if f["url"] == url), url)
    status = await message.answer("Загружаю ленту…")
    try:
        items = await feed_cache.get_or_set(url, lambda: fetcher.fetch(url, source))
    except Exception as exc:
        logger.exception("Ошибка загрузки ленты %s", url)
        await status.edit_text(f"⚠️ Не удалось загрузить ленту: {exc}")
        return
    shown = items[: config.MAX_ITEMS]
    new_items = await db.save_articles(shown)
    text = _format_news(shown, header=f"{source}: {len(shown)} свежих")
    text += f"\n\n<i>Из них новых для дайджеста: {len(new_items)}</i>"
    await status.edit_text(text, disable_web_page_preview=True)


@router.message(Command("sources"))
async def cmd_sources(message: Message) -> None:
    lines = ["🗂 <b>Встроенные ленты</b>\n"]
    lines += [f"• {_html.escape(f['name'])} — <code>{_html.escape(f['url'])}</code>" for f in config.DEFAULT_FEEDS]
    lines.append("\nСвоя лента: <code>/news https://…/rss.xml</code>")
    await message.answer("\n".join(lines))


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ("on", "off"):
        await message.answer("Использование: /digest on  или  /digest off")
        return
    on = args[1].lower() == "on"
    feed_url = config.DEFAULT_FEED_URL
    if on:
        ok = await db.subscribe(
            message.from_user.id, feed_url,
            feed_name=next(f["name"] for f in config.DEFAULT_FEEDS if f["url"] == feed_url),
        )
        if not ok:
            await message.answer("Вы уже подписаны на дайджест.")
            return
    else:
        await db.unsubscribe(message.from_user.id, feed_url)
    await message.answer(
        f"📬 Дайджест <b>{'включён' if on else 'выключен'}</b> "
        f"(каждый день в {config.DIGEST_HOUR}:00, только новые новости)."
    )


@router.message(Command("mysubs"))
async def cmd_mysubs(message: Message) -> None:
    """На какие ленты включён дайджест (подписки текущего пользователя)."""
    subs = await db.user_subscriptions(message.from_user.id)
    if not subs:
        await message.answer("Вы не подписаны на дайджест. Включить: /digest on")
        return
    lines = [
        f"• {_html.escape(s['feed_name'] or s['feed_url'], quote=False)} — "
        f"<code>{_html.escape(s['feed_url'])}</code>"
        for s in subs
    ]
    await message.answer("📬 <b>Ваши подписки на дайджест:</b>\n" + "\n".join(lines))


@router.message(Command("latest"))
async def cmd_latest(message: Message) -> None:
    rows = await db.latest(limit=10)
    if not rows:
        await message.answer("Новостей пока не сохранено. Запросите /news.")
        return
    items = [
        f"• <a href=\"{_html.escape(r['link'])}\">{_html.escape(r['title'])}</a>"
        for r in rows
    ]
    await message.answer("🗃 <b>Последние сохранённые</b>\n" + "\n".join(items),
                         disable_web_page_preview=True)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    total = await db.total_articles()
    subs = await db.all_subscriptions()
    await message.answer(
        f"📊 <b>Статистика</b>\n"
        f"• Обработано новостей: <b>{total}</b>\n"
        f"• Подписок на дайджест: <b>{len(subs)}</b>\n"
        f"• Режим: <b>{'демо' if fetcher.demo_mode else 'реальные ленты'}</b>"
    )


# ------------------------------------------------------- ежедневный дайджест

async def _digest_job() -> None:
    """Отправляет подписчикам только НОВЫЕ новости (дедупликация по link)."""
    if _bot is None:
        return
    subs = await db.all_subscriptions()
    for sub in subs:
        try:
            items = await fetcher.fetch(sub["feed_url"], sub["feed_name"])
        except Exception:
            logger.exception("Дайджест: ошибка ленты %s", sub["feed_url"])
            continue
        # save_articles возвращает только вновь добавленные
        new_items = await db.save_articles(items)
        if new_items:
            
            text = _format_news(new_items[: config.MAX_ITEMS], header=f"{sub['feed_name']}: {len(new_items)} новых")
            await _bot.send_message(sub["user_id"], text, disable_web_page_preview=True)
        await asyncio.sleep(0.3)


async def main() -> None:
    global _bot
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан NEWS_BOT_TOKEN. Скопируйте .env.example и задайте токен.")
    _bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.message.middleware(ThrottlingMiddleware(min_interval=config.THROTTLE_MIN_INTERVAL))
    dp.update.middleware(LoggingMiddleware())
    await db.init()
    scheduler.add_job(_digest_job, "cron", hour=config.DIGEST_HOUR, minute=0)
    scheduler.start()
    logger.info(
        "Новостной бот запущен. Режим: %s",
        "демо-данные" if fetcher.demo_mode else "RSS/Atom-ленты",
    )
    try:
        await dp.start_polling(_bot)
    finally:
        await _bot.session.close()
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
