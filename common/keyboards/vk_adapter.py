"""Конвертация универсальных клавиатур в формат VK API.

Адаптер преобразует :class:`~common.keyboards.models.Keyboard` в JSON-строку,
совместимую с параметром ``keyboard`` методов ``messages.send`` и
``messages.edit`` VK API (и с однотипным форматом библиотеки vkbottle).

Правила конвертации:

* ``TEXT`` → кнопка ``text`` с цветом (цвет поддерживается только у
  ``text`` и ``callback`` — у остальных типов он опускается);
* ``URL`` → кнопка ``open_link``;
* ``CALLBACK`` → кнопка ``callback``; ``callback_data`` переносится
  в payload кнопки под ключом ``callback_data`` (в объединении с payload
  приоритет у явного ``payload``);
* ``LOCATION`` → кнопка ``location`` (у кнопки геолокации в VK нет подписи —
  текст из модели не используется);
* ``PAY`` → кнопка ``vkpay`` (требуется ``payload["hash"]``, иначе —
  текстовая кнопка и предупреждение);
* ``PHONE`` → в VK не поддерживается: заменяется на текстовую кнопку
  с предупреждением в лог.

Лимиты VK API: не более 5 кнопок в строке, не более 10 строк
в обычной клавиатуре и 6 строк в inline-клавиатуре — при превышении
в лог пишется предупреждение (клавиатура всё равно сериализуется).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .models import ButtonColor, ButtonType

if TYPE_CHECKING:
    from .models import Button, Keyboard

logger = logging.getLogger(__name__)

#: Максимум кнопок в строке (VK API)
MAX_ROW_BUTTONS: int = 5
#: Максимум строк в обычной клавиатуре (VK API)
MAX_ROWS: int = 10
#: Максимум строк в inline-клавиатуре (VK API)
MAX_INLINE_ROWS: int = 6


class VKKeyboardAdapter:
    """Адаптер универсальной клавиатуры → JSON-строка VK API.

    Пример:
        >>> import json
        >>> from common.keyboards import KeyboardBuilder, VKKeyboardAdapter
        >>> keyboard = KeyboardBuilder().add_text_button("Меню").build()
        >>> data = json.loads(VKKeyboardAdapter().convert(keyboard))
        >>> data["buttons"][0][0]["action"]["label"]
        'Меню'
    """

    def convert(self, keyboard: Keyboard) -> str:
        """Конвертирует универсальную клавиатуру в JSON-строку VK API.

        Args:
            keyboard: Универсальная клавиатура :class:`~common.keyboards.models.Keyboard`.

        Returns:
            JSON-строка вида ``{"one_time": ..., "inline": ..., "buttons": [[...]]}``
            для параметра ``keyboard`` VK API. Пустые строки пропускаются.

        Raises:
            ValueError: если в клавиатуре нет ни одной кнопки.
        """
        if len(keyboard) == 0:
            raise ValueError("Нельзя конвертировать пустую клавиатуру (нет кнопок)")

        rows: list[list[dict[str, Any]]] = []
        button_count = 0
        for row_number, row in enumerate(keyboard.get_rows()):
            if not row:
                continue
            if len(row) > MAX_ROW_BUTTONS:
                logger.warning(
                    "Строка %d содержит %d кнопок — VK поддерживает не более %d "
                    "кнопок в строке",
                    row_number,
                    len(row),
                    MAX_ROW_BUTTONS,
                )
            rows.append([self._button_dict(button) for button in row])
            button_count += len(row)

        max_rows = MAX_INLINE_ROWS if keyboard.inline else MAX_ROWS
        if len(rows) > max_rows:
            logger.warning(
                "Клавиатура содержит %d строк — VK поддерживает не более %d строк "
                "(inline=%s)",
                len(rows),
                max_rows,
                keyboard.inline,
            )

        # Параметр resize VK API не поддерживает — свойство просто игнорируется
        if not keyboard.resize:
            logger.debug("Свойство resize не поддерживается VK API — игнорируется")

        data = {
            "one_time": keyboard.one_time,
            "inline": keyboard.inline,
            "buttons": rows,
        }
        result = json.dumps(data, ensure_ascii=False)
        logger.debug(
            "Конвертация в клавиатуру VK: строк=%d кнопок=%d inline=%s one_time=%s",
            len(rows),
            button_count,
            keyboard.inline,
            keyboard.one_time,
        )
        return result

    # ------------------------------------------------------------------
    # Внутренняя конвертация
    # ------------------------------------------------------------------

    def _button_dict(self, button: Button) -> dict[str, Any]:
        """Создаёт словарь одной кнопки VK API.

        Args:
            button: Кнопка в абстрактном формате.

        Returns:
            Словарь ``{"action": {...}, "color"?: ...}``.
        """
        action = self._action_dict(button)
        button_dict: dict[str, Any] = {"action": action}
        # Цвет поддерживается VK только у кнопок text и callback
        if (
            action["type"] in (ButtonType.TEXT.value, ButtonType.CALLBACK.value)
            and button.color is not ButtonColor.DEFAULT
        ):
            button_dict["color"] = button.color.value
        return button_dict

    def _action_dict(self, button: Button) -> dict[str, Any]:
        """Создаёт словарь ``action`` кнопки VK API.

        Args:
            button: Кнопка в абстрактном формате.

        Returns:
            Словарь действия кнопки (``type``, ``label``, ``payload`` и др.).
        """
        if button.type is ButtonType.URL:
            return self._with_payload(
                {
                    "type": "open_link",
                    "link": button.url,
                    "label": button.text,
                },
                button,
            )

        if button.type is ButtonType.CALLBACK:
            # callback_data переносим в payload, чтобы обработчик в VK видел
            # те же данные, что и callback-обработчик в Telegram
            merged = {"callback_data": button.callback_data, **button.payload}
            return self._with_payload(
                {"type": "callback", "label": button.text}, button, payload=merged
            )

        if button.type is ButtonType.LOCATION:
            # У геокнопки VK нет поля label — текст из модели не используется
            return self._with_payload({"type": "location"}, button)

        if button.type is ButtonType.PAY:
            pay_hash = button.payload.get("hash")
            if isinstance(pay_hash, str) and pay_hash:
                # hash переносим в действие, убирая дублирование из payload
                rest = {k: v for k, v in button.payload.items() if k != "hash"}
                return self._with_payload(
                    {"type": "vkpay", "hash": pay_hash}, button, payload=rest
                )
            logger.warning(
                "Кнопка оплаты без payload['hash'] не поддерживается VK — "
                "заменена на текстовую кнопку"
            )

        if button.type is ButtonType.PHONE:
            logger.warning(
                "Кнопка запроса телефона не поддерживается VK API — "
                "заменена на текстовую кнопку"
            )

        # TEXT, PAY без hash и PHONE — обычная текстовая кнопка
        return self._with_payload({"type": "text", "label": button.text}, button)

    @staticmethod
    def _with_payload(
        action: dict[str, Any],
        button: Button,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Добавляет к действию JSON-строку payload (формат VK API).

        Args:
            action: Словарь действия кнопки (изменяется копия).
            button: Кнопка, чей payload переносится.
            payload: Готовый словарь payload; ``None`` — взять
                ``button.payload``.

        Returns:
            Словарь действия с добавленным ``payload``, если он непуст.
        """
        source = dict(button.payload if payload is None else payload)
        if not source:
            return action
        action["payload"] = json.dumps(source, ensure_ascii=False)
        return action


__all__ = (
    "VKKeyboardAdapter",
    "MAX_ROW_BUTTONS",
    "MAX_ROWS",
    "MAX_INLINE_ROWS",
)
