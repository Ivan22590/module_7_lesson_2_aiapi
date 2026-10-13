"""Общие переиспользуемые компоненты проекта (без прикладной логики).

Публичный интерфейс — универсальные кнопочные клавиатуры, одинаковые
для Telegram- и VK-бота:

    >>> from common import KeyboardBuilder, VKKeyboardAdapter
    >>> keyboard = KeyboardBuilder().add_text_button("Меню").build()
    >>> isinstance(VKKeyboardAdapter().convert(keyboard), str)
    True

Модуль не знает о ``/tgbot``, ``/vkbot`` и ``/llm``: связывание
выполняется внешним кодом. Документация — в ``common/keyboards/README.md``.
"""

from __future__ import annotations

from .keyboards import (
    Button,
    ButtonColor,
    ButtonType,
    Keyboard,
    KeyboardBuilder,
    TelegramKeyboardAdapter,
    VKKeyboardAdapter,
)

__all__ = (
    "Button",
    "ButtonColor",
    "ButtonType",
    "Keyboard",
    "KeyboardBuilder",
    "TelegramKeyboardAdapter",
    "VKKeyboardAdapter",
)
