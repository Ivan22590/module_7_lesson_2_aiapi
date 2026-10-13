"""Универсальная система кнопочных клавиатур для Telegram и VK.

Одно и то же описание клавиатуры конвертируется адаптерами в нативные
форматы обоих мессенджеров, поэтому интерфейсы выглядят одинаково,
а модуль не содержит прикладной бизнес-логики.

Пример:
    >>> from common.keyboards import KeyboardBuilder, TelegramKeyboardAdapter
    >>> keyboard = (
    ...     KeyboardBuilder()
    ...     .add_text_button("Меню", row=0, column=0)
    ...     .add_text_button("Настройки", row=0, column=1)
    ...     .build()
    ... )
    >>> markup = TelegramKeyboardAdapter().convert(keyboard)
    >>> len(markup.keyboard)
    1

Подробнее — в README пакета: ``common/keyboards/README.md``.
"""

from __future__ import annotations

from .builder import KeyboardBuilder
from .models import Button, ButtonColor, ButtonType, Keyboard
from .telegram_adapter import TelegramKeyboardAdapter
from .vk_adapter import VKKeyboardAdapter

__all__ = (
    "Button",
    "ButtonColor",
    "ButtonType",
    "Keyboard",
    "KeyboardBuilder",
    "TelegramKeyboardAdapter",
    "VKKeyboardAdapter",
)
