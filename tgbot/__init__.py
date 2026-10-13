"""Универсальная инфраструктура Telegram-бота (aiogram, асинхронная).

Публичный интерфейс модуля:

    >>> from tgbot import TelegramBot, Router
    >>> router = Router()
    >>> @router.command("hello")
    ... async def hello(message, bot=None):
    ...     await bot.send_message(message.chat.id, "Hello!")
    >>> TelegramBot(router=router).run()

Обработчики должны быть ``async`` — бот работает на асинхронном
event loop aiogram.

Модуль не содержит бизнес-логики и не зависит от ``/llm``: связывание
бота с нейросетью выполняется в внешнем проекте через обработчики.
"""

from __future__ import annotations

from .bot import TelegramBot
from .config import ConfigError, TelegramConfig
from .filters import all_of, any_text, callback_prefix, commands, regexp
from .fsm import extract_user_id, make_states_middleware, state_is, state_is_none
from .handlers import build_service_router
from .middlewares import describe_incoming, describe_outgoing, install_logging
from .router import Router
from .utils import preview, safe_handler

__all__ = (
    "TelegramBot",
    "TelegramConfig",
    "ConfigError",
    "Router",
    "build_service_router",
    "install_logging",
    "describe_incoming",
    "describe_outgoing",
    "commands",
    "regexp",
    "any_text",
    "callback_prefix",
    "all_of",
    "state_is",
    "state_is_none",
    "extract_user_id",
    "make_states_middleware",
    "preview",
    "safe_handler",
)
