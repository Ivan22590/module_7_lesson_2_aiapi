"""Служебные утилиты Telegram-бота: безопасная обёртка обработчиков и лог-превью."""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Максимальная длина фрагмента текста в строке лога
PREVIEW_LIMIT: int = 300


def preview(value: Any, limit: int = PREVIEW_LIMIT) -> str:
    """Сжимает значение до однострочной строки для записи в лог.

    Переводы строк заменяются пробелами, слишком длинный текст обрезается
    многоточием — лог остаётся читаемым.

    Args:
        value: Любое значение (текст сообщения, объект и т.п.).
        limit: Максимальная длина результата.

    Returns:
        Однострочное представление значения.
    """
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def extract_chat_id(obj: Any) -> int | None:
    """Извлекает ``chat_id`` из сообщения или callback-запроса.

    Args:
        obj: Сообщение ``aiogram.types.Message`` или
            ``aiogram.types.CallbackQuery``.

    Returns:
        Идентификатор чата или ``None``, если его не удалось определить.
    """
    chat = getattr(obj, "chat", None)
    if chat is not None and hasattr(chat, "id"):
        return int(chat.id)
    message = getattr(obj, "message", None)
    if message is not None:
        chat = getattr(message, "chat", None)
        if chat is not None and hasattr(chat, "id"):
            return int(chat.id)
    return None


async def notify_error(args: tuple, bot: Any, text: str) -> None:
    """Отправляет пользователю дружелюбное сообщение об ошибке.

    Args:
        args: Позиционные аргументы обработчика (сообщение или callback).
        bot: Экземпляр ``aiogram.Bot`` (может быть ``None``).
        text: Текст сообщения об ошибке.
    """
    if bot is None or not args:
        return
    try:
        chat_id = extract_chat_id(args[0])
        if chat_id is not None:
            result = bot.send_message(chat_id, text)
            if inspect.isawaitable(result):
                await result
    except Exception:  # noqa: BLE001 - уведомление не должно ронять бота
        logger.exception("Не удалось отправить сообщение об ошибке")


def safe_handler(
    func: Callable[..., Any] | None = None,
    *,
    error_text: str = "⚠️ Произошла непредвиденная ошибка. Попробуйте ещё раз.",
) -> Callable[..., Any]:
    """Оборачивает обработчик в try/except с логированием и ответом пользователю.

    Можно использовать и напрямую (``@safe_handler``), и с параметром текста
    (``@safe_handler(error_text="...")``). Обёртка всегда async: обёрнутая
    функция может быть и sync, и async — awaitable-результат будет awaited.
    Чтобы бот мог ответить, объект бота должен прийти в ``kwargs['bot']``.

    Args:
        func: Исходный обработчик (если ``None`` — возвращается декоратор
            с настройками).
        error_text: Текст, который увидит пользователь при ошибке.

    Returns:
        Async-обёрнутый обработчик или декоратор.
    """

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(target)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = target(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception:  # noqa: BLE001 - обработчик не должен ронять polling
                logger.exception("Необработанное исключение в %s", target.__name__)
                await notify_error(args, kwargs.get("bot"), error_text)
                return None

        return wrapper

    return decorate if func is None else decorate(func)


__all__ = ("preview", "extract_chat_id", "notify_error", "safe_handler", "PREVIEW_LIMIT")
