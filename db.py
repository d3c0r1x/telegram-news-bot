"""SQLite-БД новостного бота (aiosqlite).

Схема:
  articles(id PK, title, link UNIQUE, published, source, created_at)
      — link UNIQUE = дедупликация: одна и та же новость не попадёт
        в дайджест дважды, даже если лента обновилась заново.
  subscriptions(user_id, feed_url, feed_name, UNIQUE(user_id, feed_url))
      — подписки на ежедневный дайджест.
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str = config.DB_PATH) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS articles ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " title TEXT NOT NULL,"
                " link TEXT NOT NULL UNIQUE,"
                " published TEXT NOT NULL DEFAULT '',"
                " source TEXT NOT NULL DEFAULT '',"
                " created_at TEXT NOT NULL)"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS subscriptions ("
                " user_id INTEGER NOT NULL,"
                " feed_url TEXT NOT NULL,"
                " feed_name TEXT NOT NULL DEFAULT '',"
                " UNIQUE(user_id, feed_url))"
            )
            await db.commit()

    async def save_articles(self, items: list) -> list:
        """INSERT OR IGNORE — вставляет только новые.

        Возвращает список ТОЛЬКО вновь добавленных элементов (в порядке
        исходного списка) — по нему рассылается дайджест: старые новости,
        уже бывшие в БД, в него не попадут.
        """
        inserted: list = []
        async with aiosqlite.connect(self.path) as db:
            for it in items:
                cur = await db.execute(
                    "INSERT OR IGNORE INTO articles (title, link, published, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (it.title, it.link, it.published, it.source, _now()),
                )
                if cur.rowcount > 0:
                    inserted.append(it)
            await db.commit()
        return inserted

    async def latest(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM articles ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def total_articles(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM articles")
            row = await cur.fetchone()
        return int(row[0])

    # -------------------------------------------------------- подписки

    async def subscribe(self, user_id: int, feed_url: str, feed_name: str = "") -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO subscriptions (user_id, feed_url, feed_name) "
                "VALUES (?, ?, ?)",
                (user_id, feed_url, feed_name),
            )
            await db.commit()
            return cur.rowcount > 0

    async def unsubscribe(self, user_id: int, feed_url: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM subscriptions WHERE user_id = ? AND feed_url = ?",
                (user_id, feed_url),
            )
            await db.commit()
            return cur.rowcount > 0

    async def user_subscriptions(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT feed_url, feed_name FROM subscriptions WHERE user_id = ? ORDER BY feed_name",
                (user_id,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def all_subscriptions(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM subscriptions ORDER BY user_id")
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
