"""Конвертация универсальных клавиатур в формат Telegram Bot API.

Адаптер преобразует :class:`~common.keyboards.models.Keyboard` в объекты
``ReplyKeyboardMarkup`` или ``InlineKeyboardMarkup`` библиотеки aiogram.
Импорт aiogram выполняется лениво (внутри :meth:`TelegramKeyboardAdapter.convert`),
поэтому пакет ``common`` можно импортировать в проекте, где aiogram
не установлен.

Правила конвертации:

* reply-клавиатура: ``TEXT``/``CALLBACK``/``URL``/``PAY`` → обычная кнопка
  с текстом, ``LOCATION`` → кнопка с запросом геолокации,
  ``PHONE`` → кнопка с запросом контакта;
* inline-клавиатура: ``CALLBACK`` → ``callback_data``, ``URL`` → ``url``,
  ``TEXT`` → callback-кнопка с текстом в качестве данных, ``LOCATION``/
  ``PHONE``/``PAY`` → callback-кнопка с текстом (fallback с предупреждением);
* ``callback_data`` длиннее 64 байт усекается с предупреждением в лог.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

    from .models import Button, Keyboard

logger = logging.getLogger(__name__)

#: Максимальная длина callback_data в Telegram, байт
CALLBACK_DATA_LIMIT_BYTES: int = 64


class TelegramKeyboardAdapter:
    """Адаптер универсальной клавиатуры → объекты Telegram Bot API (aiogram).

    Пример:
        >>> from common.keyboards import KeyboardBuilder, TelegramKeyboardAdapter
        >>> keyboard = KeyboardBuilder().add_text_button("Меню").build()
        >>> markup = TelegramKeyboardAdapter().convert(keyboard)
        >>> markup.keyboard[0][0].text
        'Меню'
    """

    def convert(self, keyboard: Keyboard) -> ReplyKeyboardMarkup | InlineKeyboardMarkup:
        """Конвертирует универсальную клавиатуру в объект aiogram.

        Args:
            keyboard: Универсальная клавиатура :class:`~common.keyboards.models.Keyboard`.

        Returns:
            ``InlineKeyboardMarkup`` для inline-клавиатуры, иначе
            ``ReplyKeyboardMarkup``. Пустые строки пропускаются.

        Raises:
            ValueError: если в клавиатуре нет ни одной кнопки.
        """
        # Ленивый импорт: aiogram нужен только при конвертации
        from aiogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            KeyboardButton,
            ReplyKeyboardMarkup,
        )

        if len(keyboard) == 0:
            raise ValueError("Нельзя конвертировать пустую клавиатуру (нет кнопок)")

        if keyboard.inline:
            rows = [
                [
                    self._inline_button(button, InlineKeyboardButton)
                    for button in row
                ]
                for row in keyboard.get_rows()
                if row
            ]
            logger.debug(
                "Конвертация в inline-клавиатуру Telegram: строк=%d кнопок=%d",
                keyboard.row_count(),
                len(keyboard),
            )
            return InlineKeyboardMarkup(inline_keyboard=rows)

        rows = [
            [self._reply_button(button, KeyboardButton) for button in row]
            for row in keyboard.get_rows()
            if row
        ]
        logger.debug(
            "Конвертация в reply-клавиатуру Telegram: строк=%d кнопок=%d "
            "resize=%s one_time=%s",
            keyboard.row_count(),
            len(keyboard),
            keyboard.resize,
            keyboard.one_time,
        )
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=keyboard.resize,
            one_time_keyboard=keyboard.one_time,
        )

    # ------------------------------------------------------------------
    # Внутренняя конвертация
    # ------------------------------------------------------------------

    def _reply_button(self, button: Button, button_type: Any) -> Any:
        """Создаёт ``KeyboardButton`` для reply-клавиатуры Telegram.

        Args:
            button: Кнопка в абстрактном формате.
            button_type: Класс ``aiogram.types.KeyboardButton``.

        Returns:
            Объект ``KeyboardButton``.
        """
        from .models import ButtonType

        if button.type is ButtonType.LOCATION:
            return button_type(text=button.text, request_location=True)
        if button.type is ButtonType.PHONE:
            return button_type(text=button.text, request_contact=True)
        if button.type in (ButtonType.CALLBACK, ButtonType.URL, ButtonType.PAY):
            logger.warning(
                "Кнопка типа %s не поддерживается в reply-клавиатуре Telegram — "
                "используется обычная текстовая кнопка",
                button.type.value,
            )
        return button_type(text=button.text)

    def _inline_button(self, button: Button, button_type: Any) -> Any:
        """Создаёт ``InlineKeyboardButton`` для inline-клавиатуры Telegram.

        Args:
            button: Кнопка в абстрактном формате.
            button_type: Класс ``aiogram.types.InlineKeyboardButton``.

        Returns:
            Объект ``InlineKeyboardButton``.
        """
        from .models import ButtonType

        if button.type is ButtonType.URL and button.url:
            return button_type(text=button.text, url=button.url)

        if button.type is ButtonType.CALLBACK and button.callback_data:
            data = self._fit_callback_data(button.callback_data)
            return button_type(text=button.text, callback_data=data)

        if button.type is ButtonType.TEXT:
            # По спецификации задачи: текст TEXT-кнопки становится callback-данными
            return button_type(
                text=button.text,
                callback_data=self._fit_callback_data(button.text),
            )

        logger.warning(
            "Кнопка типа %s не поддерживается в inline-клавиатуре Telegram — "
            "используется callback-кнопка с текстом в качестве данных",
            button.type.value,
        )
        return button_type(
            text=button.text,
            callback_data=self._fit_callback_data(button.text),
        )

    @staticmethod
    def _fit_callback_data(data: str) -> str:
        """Ограничивает callback_data лимитом Telegram (64 байта).

        Args:
            data: Исходное значение callback-данных.

        Returns:
            Значение, усечённое до 64 байт (русские символы не режутся
            посреди — обрезка идёт по байтам с игнорированием остатка).
        """
        encoded = data.encode("utf-8")
        if len(encoded) <= CALLBACK_DATA_LIMIT_BYTES:
            return data
        fitted = encoded[:CALLBACK_DATA_LIMIT_BYTES].decode("utf-8", errors="ignore")
        logger.warning(
            "callback_data длиннее %d байт (длина %d) — значение усечено",
            CALLBACK_DATA_LIMIT_BYTES,
            len(encoded),
        )
        return fitted


__all__ = ("TelegramKeyboardAdapter", "CALLBACK_DATA_LIMIT_BYTES")
