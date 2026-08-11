"""Интеграционный тест сценария подписок на дайджест (команда /mysubs).

Апдейты прогоняются через НАСТОЯЩИЙ Dispatcher (router и хендлеры bot.py),
исходящие вызовы Bot API перехватываются CapturingSession — сеть не нужна.
Сценарий: /mysubs (пусто) → /digest on → /mysubs (подписка видна) →
/digest off → /mysubs (снова пусто).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as botmod  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import Chat, Message, Update, User  # noqa: E402
from db import Database  # noqa: E402
from middlewares import LoggingMiddleware, ThrottlingMiddleware  # noqa: E402

USER_ID = 555
FAKE_TOKEN = "12345:test-only-no-network"


class CapturingSession(BaseSession):
    """Перехватывает исходящие вызовы Bot API и записывает их в self.calls."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ):
        data = method.model_dump(exclude_none=True)
        self.calls.append({"method": type(method).__name__, "data": data})
        if type(method).__name__ == "SendMessage":
            return Message(
                message_id=1,
                date=datetime.now(),
                chat=Chat(id=USER_ID, type="private"),
                text=data.get("text", ""),
            )
        return True

    async def close(self) -> None:
        return None

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


def _user() -> User:
    return User(id=USER_ID, is_bot=False, first_name="News", username="news_tester")


def _chat() -> Chat:
    return Chat(id=USER_ID, type="private")


def _msg(text: str, mid: int, upd: int) -> Update:
    return Update(
        update_id=upd,
        message=Message(
            message_id=mid,
            date=datetime.now(),
            chat=_chat(),
            from_user=_user(),
            text=text,
        ),
    )


def _texts(session: CapturingSession) -> list[str]:
    return [c["data"].get("text", "") for c in session.calls if c["method"] == "SendMessage"]


# Роутер бота можно прикрепить только к ОДНОМУ Dispatcher'у (aiogram кидает
# RuntimeError при повторном include_router) — создаём один раз на модуль.
DP = Dispatcher()
DP.include_router(botmod.router)
DP.message.middleware(ThrottlingMiddleware(min_interval=0.0))
DP.update.middleware(LoggingMiddleware())


def test_digest_subscriptions_flow(tmp_path) -> None:
    """/mysubs показывает и скрывает подписки на дайджест пользователя."""
    db_path = str(tmp_path / "news.db")

    async def run() -> None:
        botmod.db = Database(db_path)
        await botmod.db.init()
        session = CapturingSession()
        bot = Bot(
            token=FAKE_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=session,
        )
        upd = mid = 0

        # /mysubs до подписки — понятный ответ
        await DP.feed_update(bot, _msg("/mysubs", mid := mid + 1, upd := upd + 1))
        assert any("не подписаны на дайджест" in t for t in _texts(session))

        # /digest on — подписка создана
        session.calls.clear()
        await DP.feed_update(bot, _msg("/digest on", mid := mid + 1, upd := upd + 1))
        assert any("Дайджест <b>включён</b>" in t for t in _texts(session))

        # /mysubs — подписка видна (имя ленты + URL)
        session.calls.clear()
        await DP.feed_update(bot, _msg("/mysubs", mid := mid + 1, upd := upd + 1))
        texts = _texts(session)
        assert any("Ваши подписки на дайджест" in t for t in texts)
        assert any("Lenta.ru" in t and "lenta.ru/rss" in t for t in texts)

        # /digest off — отписка; /mysubs снова пуст
        session.calls.clear()
        await DP.feed_update(bot, _msg("/digest off", mid := mid + 1, upd := upd + 1))
        assert any("Дайджест <b>выключен</b>" in t for t in _texts(session))
        session.calls.clear()
        await DP.feed_update(bot, _msg("/mysubs", mid := mid + 1, upd := upd + 1))
        assert any("не подписаны на дайджест" in t for t in _texts(session))

        await bot.session.close()

    asyncio.run(run())
