"""Служебные обработчики Telegram-бота.

Это минимальные заглушки для проверки работоспособности (``/start``,
``/help``, echo) — НЕ продуктовый функционал. Они регистрируются последними,
поэтому любые обработчики внешнего проекта имеют приоритет.
"""

from __future__ import annotations

import logging
from typing import Any

from .router import Router
from .utils import safe_handler

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Это универсальный Telegram-бот.\n\n"
    "Доступные команды:\n"
    "/start — приветствие,\n"
    "/help — эта справка.\n\n"
    "Любое другое сообщение бот вернёт эхом."
)

START_TEXT = "Привет! Я служебный Telegram-бот. Отправь /help, чтобы узнать больше."


def build_service_router() -> Router:
    """Создаёт роутер со служебными обработчиками по умолчанию.

    Returns:
        Роутер с командами ``/start``, ``/help`` и echo-обработчиком.
    """
    router = Router()

    @router.command("start")
    @safe_handler
    async def handle_start(message: object, bot: Any = None) -> None:
        """Отвечает приветствием на команду /start."""
        chat_id = message.chat.id  # type: ignore[attr-defined]
        await bot.send_message(chat_id, START_TEXT)
        logger.debug("Отправлено приветствие chat=%s", chat_id)

    @router.command("help")
    @safe_handler
    async def handle_help(message: object, bot: Any = None) -> None:
        """Отвечает справкой на команду /help."""
        chat_id = message.chat.id  # type: ignore[attr-defined]
        await bot.send_message(chat_id, HELP_TEXT)
        logger.debug("Отправлена справка chat=%s", chat_id)

    @router.message()
    @safe_handler
    async def handle_echo(message: object, bot: Any = None) -> None:
        """Возвращает пользователю текст сообщения (echo-заглушка)."""
        chat_id = message.chat.id  # type: ignore[attr-defined]
        text = getattr(message, "text", "") or ""
        await bot.send_message(chat_id, f"Вы написали: {text}")

    return router


__all__ = ("build_service_router", "START_TEXT", "HELP_TEXT")
