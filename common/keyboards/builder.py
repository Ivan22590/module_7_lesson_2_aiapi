"""Цепочечный построитель универсальных клавиатур.

Пример:
    >>> keyboard = (
    ...     KeyboardBuilder()
    ...     .add_text_button("Меню", row=0, column=0)
    ...     .add_text_button("Настройки", row=0, column=1)
    ...     .add_callback_button("Действие", "action_1", row=2, column=0)
    ...     .build()
    ... )
    >>> len(keyboard)
    3
"""

from __future__ import annotations

from .models import Button, ButtonColor, ButtonType, Keyboard


class KeyboardBuilder:
    """Построитель клавиатур через цепочку вызовов.

    Каждый метод ``add_*_button`` возвращает сам построитель, поэтому
    вызовы можно записывать цепочкой, а метод :meth:`build` возвращает
    готовую :class:`~common.keyboards.models.Keyboard`.
    """

    def __init__(
        self,
        *,
        inline: bool = False,
        one_time: bool = False,
        resize: bool = True,
    ) -> None:
        """Создаёт пустой построитель клавиатуры.

        Args:
            inline: Строить inline-клавиатуру (под сообщением).
            one_time: Прятать клавиатуру после нажатия кнопки.
            resize: Автоматически уменьшать клавиатуру (поддерживает Telegram;
                VK это свойство игнорирует).
        """
        self._keyboard: Keyboard = Keyboard(
            one_time=one_time, resize=resize, inline=inline
        )

    def add_button(self, button: Button) -> KeyboardBuilder:
        """Добавляет готовую кнопку в абстрактном формате.

        Args:
            button: Кнопка :class:`~common.keyboards.models.Button`.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(button)
        return self

    def add_text_button(
        self,
        text: str,
        row: int | None = None,
        column: int | None = None,
        *,
        color: ButtonColor = ButtonColor.DEFAULT,
        payload: dict | None = None,
    ) -> KeyboardBuilder:
        """Добавляет обычную текстовую кнопку.

        Args:
            text: Подпись кнопки.
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.
            color: Цвет кнопки (влияет только на VK).
            payload: Произвольные данные кнопки (словарь).

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(
                text=text,
                type=ButtonType.TEXT,
                payload=dict(payload or {}),
                row=row,
                column=column,
                color=color,
            )
        )
        return self

    def add_url_button(
        self,
        text: str,
        url: str,
        row: int | None = None,
        column: int | None = None,
    ) -> KeyboardBuilder:
        """Добавляет кнопку со ссылкой.

        Args:
            text: Подпись кнопки.
            url: Ссылка, открываемая по нажатию (``https://...``).
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(
                text=text,
                type=ButtonType.URL,
                url=url,
                row=row,
                column=column,
            )
        )
        return self

    def add_callback_button(
        self,
        text: str,
        callback_data: str,
        row: int | None = None,
        column: int | None = None,
        *,
        color: ButtonColor = ButtonColor.DEFAULT,
        payload: dict | None = None,
    ) -> KeyboardBuilder:
        """Добавляет callback-кнопку (данные уходят обработчику).

        Args:
            text: Подпись кнопки.
            callback_data: Данные кнопки. В Telegram — не более 64 байт
                (длинные значения усекаются адаптером с предупреждением).
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.
            color: Цвет кнопки (влияет только на VK).
            payload: Произвольные данные кнопки (словарь). В VK они
                объединяются с ``callback_data`` в payload кнопки.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(
                text=text,
                type=ButtonType.CALLBACK,
                callback_data=callback_data,
                payload=dict(payload or {}),
                row=row,
                column=column,
                color=color,
            )
        )
        return self

    def add_location_button(
        self,
        text: str,
        row: int | None = None,
        column: int | None = None,
    ) -> KeyboardBuilder:
        """Добавляет кнопку запроса геолокации.

        Args:
            text: Подпись кнопки (в VK геолокационная кнопка текста не имеет —
                подпись используется как есть в Telegram).
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(text=text, type=ButtonType.LOCATION, row=row, column=column)
        )
        return self

    def add_phone_button(
        self,
        text: str,
        row: int | None = None,
        column: int | None = None,
    ) -> KeyboardBuilder:
        """Добавляет кнопку запроса номера телефона.

        Args:
            text: Подпись кнопки.
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(text=text, type=ButtonType.PHONE, row=row, column=column)
        )
        return self

    def add_pay_button(
        self,
        text: str,
        row: int | None = None,
        column: int | None = None,
        *,
        payload: dict | None = None,
    ) -> KeyboardBuilder:
        """Добавляет кнопку оплаты.

        В VK для кнопки оплаты требуется ``payload["hash"]`` — параметр
        платёжной ссылки VK Pay. Без него адаптер VK заменит кнопку
        на текстовую и запишет предупреждение в лог.

        Args:
            text: Подпись кнопки.
            row: Номер строки (с нуля); ``None`` — автострока.
            column: Номер колонки (с нуля); ``None`` — автоопределение.
            payload: Данные кнопки; для VK Pay — словарь с ключом ``hash``.

        Returns:
            Тот же построитель (для цепочки вызовов).
        """
        self._keyboard.add(
            Button(
                text=text,
                type=ButtonType.PAY,
                payload=dict(payload or {}),
                row=row,
                column=column,
            )
        )
        return self

    def build(self) -> Keyboard:
        """Возвращает готовую клавиатуру.

        Returns:
            Независимая копия клавиатуры: последующие вызовы построителя
            не изменят уже построенную клавиатуру.
        """
        return Keyboard(
            buttons=list(self._keyboard.buttons),
            one_time=self._keyboard.one_time,
            resize=self._keyboard.resize,
            inline=self._keyboard.inline,
        )


__all__ = ("KeyboardBuilder",)
