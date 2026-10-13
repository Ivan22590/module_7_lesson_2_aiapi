"""Фильтры для сопоставления апдейтов с обработчиками.

Фильтры — это простые предикаты над текстом сообщения или данными
callback-запроса. Они работают и с объектами aiogram (``Message``,
``CallbackQuery``), и с любыми похожими объектами. Роутер использует их,
но внешний проект может применять их и самостоятельно.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

#: Предикат: принимает апдейт и возвращает True, если обработчик подходит
Filter = Callable[[Any], bool]


def commands(*names: str) -> Filter:
    """Создаёт фильтр команд (``/start``, ``help`` и т.п.).

    Регистронезависимо, ведущий ``/`` необязателен (сам роутер ``/tgbot``
    дополнительно требует слэш — как в прежнем telebot-поведении).

    Args:
        *names: Имена команд без слэша (``"start"``, ``"help"``).

    Returns:
        Предикат, проверяющий текст сообщения.
    """
    normalized = {name.strip().lstrip("/").lower() for name in names}

    def check(update: Any) -> bool:
        text = getattr(update, "text", None)
        if not isinstance(text, str):
            return False
        command = text.strip().split()[0].lower() if text.strip() else ""
        return command.lstrip("/").split("@")[0] in normalized

    return check


def regexp(pattern: str) -> Filter:
    """Создаёт фильтр по регулярному выражению над текстом сообщения.

    Args:
        pattern: Выражение ``re`` (компилируется один раз).

    Returns:
        Предикат, проверяющий текст сообщения.
    """
    compiled = re.compile(pattern)

    def check(update: Any) -> bool:
        text = getattr(update, "text", None)
        return bool(isinstance(text, str) and compiled.search(text))

    return check


def any_text(update: Any) -> bool:
    """Проверяет, что апдейт — непустое текстовое сообщение.

    Args:
        update: Объект сообщения (``aiogram.types.Message``).

    Returns:
        ``True``, если у сообщения есть непустой текст.
    """
    text = getattr(update, "text", None)
    return bool(isinstance(text, str) and text.strip())


def callback_prefix(*prefixes: str) -> Filter:
    """Создаёт фильтр callback-запросов по префиксу ``data``.

    Args:
        *prefixes: Допустимые префиксы (например ``"menu:"``).

    Returns:
        Предикат над объектом ``CallbackQuery``.
    """
    items: tuple[str, ...] = prefixes

    def check(update: Any) -> bool:
        data = getattr(update, "data", None)
        if not isinstance(data, str):
            return False
        return any(data.startswith(prefix) for prefix in items)

    return check


def all_of(*filters: Filter) -> Filter:
    """Объединяет фильтры по логическому «И».

    Args:
        *filters: Исходные фильтры.

    Returns:
        Предикат, истинный только если все фильтры истинны.
    """
    items: Iterable[Filter] = filters

    def check(update: Any) -> bool:
        return all(item(update) for item in items)

    return check


__all__ = ("Filter", "commands", "regexp", "any_text", "callback_prefix", "all_of")
