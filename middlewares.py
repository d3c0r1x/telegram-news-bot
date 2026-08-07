"""Middlewares: троттлинг и логирование (общий паттерн для всех ботов)."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, Update

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Пропускает не чаще одного сообщения пользователя за min_interval сек.

    Продвинутый приём: «burst» — если пользователь спамит, после короткой
    паузы даём ему ответить ещё раз (иначе атака «замолчи навсегда»).
    """

    def __init__(self, min_interval: float = 0.7, burst: int = 5) -> None:
        super().__init__()
        self._min_interval = min_interval
        self._burst = burst
        self._last: dict[int, float] = {}
        self._streak: dict[int, int] = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        message: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = message.from_user.id if message.from_user else 0
        now = time.monotonic()
        last = self._last.get(user_id, 0.0)
        if now - last < self._min_interval:
            streak = self._streak.get(user_id, 0) + 1
            self._streak[user_id] = streak
            if streak <= self._burst:
                self._last[user_id] = now
                return await handler(message, data)
            return None  # явный дроп спама
        self._last[user_id] = now
        self._streak[user_id] = 0
        return await handler(message, data)


class LoggingMiddleware(BaseMiddleware):
    """Пишет каждое входящее обновление в лог — полезно для отладки."""

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        update: Update,
        data: dict[str, Any],
    ) -> Any:
        logger.debug("Update: %s", update.model_dump(exclude_unset=True))
        return await handler(update, data)
