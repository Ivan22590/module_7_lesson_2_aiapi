"""Промежуточные слои Telegram-бота: сквозное логирование обмена с API.

Модуль универсален: он не знает ни о продуктовых сценариях, ни о нейросети —
только фиксирует, что пришло от пользователя и что ответил бот.

Реализация на aiogram:

* входящие апдейты логируются outer-middleware уровня диспетчера;
* исходящие вызовы — middleware сессии бота, которое ловит **все** методы
  Telegram API (отправка, редактирование, ответы на кнопки и т.п.).
"""

from __future__ import annotations

import logging
from typing import Any

from .utils import preview

logger = logging.getLogger(__name__)


def describe_incoming(update: Any) -> str:
    """Формирует читаемое описание входящего апдейта.

    Args:
        update: Объект ``aiogram.types.Update``.

    Returns:
        Строка вида ``message | user=... | chat=... | text=...``.
    """
    message = getattr(update, "message", None)
    if message is not None:
        user = getattr(message, "from_user", None)
        return (
            f"message | user={getattr(user, 'id', '?')}"
            f" (@{getattr(user, 'username', None) or '—'})"
            f" | chat={getattr(getattr(message, 'chat', None), 'id', '?')}"
            f" | text={preview(getattr(message, 'text', None), 120)!r}"
        )

    call = getattr(update, "callback_query", None)
    if call is not None:
        user = getattr(call, "from_user", None)
        chat = getattr(getattr(call, "message", None), "chat", None)
        return (
            f"callback | user={getattr(user, 'id', '?')}"
            f" (@{getattr(user, 'username', None) or '—'})"
            f" | chat={getattr(chat, 'id', '?')}"
            f" | data={preview(getattr(call, 'data', None), 120)!r}"
        )

    return f"прочий апдейт | update_id={getattr(update, 'update_id', '?')}"


def describe_outgoing(method: Any) -> str:
    """Формирует описание исходящего вызова Telegram API для лога.

    Args:
        method: Объект метода aiogram (``aiogram.methods.SendMessage``,
            ``EditMessageText`` и т.п.) — готовый запрос к Bot API.

    Returns:
        Однострочное описание вызова: адресат, текст, кнопки.
    """
    name = _method_name(method)

    if name == "answerCallbackQuery":
        return (
            f"callback_query_id={getattr(method, 'callback_query_id', '?')} "
            f"text={preview(getattr(method, 'text', None), 120)!r}"
        )

    if name == "editMessageText":
        return (
            f"chat={getattr(method, 'chat_id', '?')} "
            f"msg={getattr(method, 'message_id', '?')} "
            f"text={preview(getattr(method, 'text', None))!r}"
        )

    if name == "editMessageReplyMarkup":
        markup = getattr(method, "reply_markup", None)
        state = "задана" if markup is not None else "убрана"
        return (
            f"chat={getattr(method, 'chat_id', '?')} "
            f"msg={getattr(method, 'message_id', '?')} markup={state}"
        )

    # sendMessage, copyMessage и прочие методы с chat_id/text
    return (
        f"chat={getattr(method, 'chat_id', '?')} "
        f"text={preview(getattr(method, 'text', None))!r}"
    )


def _method_name(method: Any) -> str:
    """Возвращает имя метода Telegram Bot API (``sendMessage`` и т.п.).

    Args:
        method: Объект метода aiogram.

    Returns:
        Имя метода в Bot API (или имя класса, если имени нет).
    """
    return getattr(method, "__api_method__", None) or type(method).__name__


async def _log_incoming(handler: Any, event: Any, data: Any) -> Any:
    """Outer-middleware диспетчера: записывает входящий апдейт в лог.

    Args:
        handler: Следующий шаг цепочки (обработчик).
        event: Входящее событие (``aiogram.types.Update``).
        data: Контекстные данные aiogram.

    Returns:
        Результат обработки события.
    """
    try:
        logger.info("вход | %s", describe_incoming(event))
    except Exception:  # noqa: BLE001 - описание не должно ронять обработку
        logger.exception("Не удалось описать входящий апдейт")
    return await handler(event, data)


def install_logging(dispatcher: Any, bot: Any) -> None:
    """Подключает сквозное логирование входящих апдейтов и ответов бота.

    Поэтому в логе видна полная картина диалога: что прислал пользователь
    и что ответил бот.

    Args:
        dispatcher: Экземпляр ``aiogram.Dispatcher``.
        bot: Экземпляр ``aiogram.Bot``.
    """
    dispatcher.update.outer_middleware(_log_incoming)

    async def log_outgoing(next_call: Any, current_bot: Any, method: Any) -> Any:
        name = _method_name(method)
        description = describe_outgoing(method)
        try:
            result = await next_call(current_bot, method)
        except Exception:  # noqa: BLE001 - лог не должен менять поведение
            logger.exception("Ошибка отправки %s | %s", name, description)
            raise
        logger.info("ответ %s | %s", name, description)
        return result

    bot.session.middleware(log_outgoing)
    logger.debug("Сквозное логирование подключено")


__all__ = ("install_logging", "describe_incoming", "describe_outgoing")
