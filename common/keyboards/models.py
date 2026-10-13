"""Абстрактные модели кнопок и клавиатур.

Модели не знают о Telegram и VK: платформенные особенности инкапсулированы
в адаптерах (:mod:`common.keyboards.telegram_adapter` и
:mod:`common.keyboards.vk_adapter`), поэтому одна и та же клавиатура
выглядит одинаково в обоих ботах.

Пример:
    >>> from common.keyboards import KeyboardBuilder
    >>> keyboard = KeyboardBuilder().add_text_button("Меню").build()
    >>> keyboard.row_count()
    1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ButtonType(str, Enum):
    """Тип кнопки — определяет её поведение в мессенджерах.

    Attributes:
        TEXT: обычная текстовая кнопка.
        URL: кнопка, открывающая ссылку.
        CALLBACK: кнопка, отправляющая обработчику callback-данные.
        LOCATION: кнопка запроса геолокации пользователя.
        PHONE: кнопка запроса номера телефона пользователя.
        PAY: кнопка оплаты (поддерживается не всеми платформами).
    """

    TEXT = "text"
    URL = "url"
    CALLBACK = "callback"
    LOCATION = "location"
    PHONE = "phone"
    PAY = "pay"


class ButtonColor(str, Enum):
    """Цвет кнопки (цвета VK; Telegram не поддерживает цвета кнопок).

    Attributes:
        DEFAULT: цвет платформы по умолчанию (без явного цвета).
        PRIMARY: акцентный (в VK — синий).
        SECONDARY: нейтральный (серый).
        POSITIVE: положительный (зелёный).
        NEGATIVE: отрицательный (красный).
    """

    DEFAULT = "default"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True)
class Button:
    """Одна кнопка в абстрактном формате.

    Attributes:
        text: Подпись кнопки (отображается пользователю).
        type: Тип кнопки (см. :class:`ButtonType`).
        payload: Произвольные данные кнопки — доставляются обработчику там,
            где платформа это позволяет (например, в payload VK).
        row: Номер строки (с нуля). ``None`` — кнопка встанет в отдельную
            новую строку ниже всех явно заданных.
        column: Номер колонки (с нуля) внутри строки. ``None`` — кнопка
            встанет после кнопок с явной колонкой (в порядке добавления).
        color: Цвет кнопки. Используется в VK; Telegram цвета игнорирует.
        url: Ссылка — обязательна для кнопок :attr:`ButtonType.URL`.
        callback_data: Данные callback-кнопки :attr:`ButtonType.CALLBACK`.
            В Telegram ограничены 64 байтами (адаптер усекает с предупреждением).

    Raises:
        ValueError: если параметры некорректны: пустой текст, отрицательные
            строка/колонка, ``URL`` без адреса, ``CALLBACK`` без данных
            либо неизвестный тип/цвет.
    """

    text: str
    type: ButtonType = ButtonType.TEXT
    payload: dict[str, Any] = field(default_factory=dict)
    row: int | None = None
    column: int | None = None
    color: ButtonColor = ButtonColor.DEFAULT
    url: str | None = None
    callback_data: str | None = None

    def __post_init__(self) -> None:
        """Проверяет корректность параметров кнопки."""
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(
                f"Текст кнопки должен быть непустой строкой, получено: {self.text!r}"
            )
        if not isinstance(self.type, ButtonType):
            raise ValueError(
                f"Неизвестный тип кнопки: {self.type!r}; ожидается один из ButtonType"
            )
        if not isinstance(self.color, ButtonColor):
            raise ValueError(
                f"Неизвестный цвет кнопки: {self.color!r}; ожидается один из ButtonColor"
            )
        for name, value in (("row", self.row), ("column", self.column)):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(
                    f"Параметр {name} должен быть целым числом >= 0, получено: {value!r}"
                )
        if not isinstance(self.payload, dict):
            raise ValueError(
                "payload должен быть словарём, получено: "
                f"{type(self.payload).__name__}"
            )
        if self.type is ButtonType.URL and not self.url:
            raise ValueError("Для кнопки типа URL должен быть задан параметр url")
        if self.type is ButtonType.CALLBACK and not self.callback_data:
            raise ValueError(
                "Для кнопки типа CALLBACK должен быть задан параметр callback_data"
            )


@dataclass
class Keyboard:
    """Универсальная кнопочная клавиатура.

    Кнопки хранятся плоским списком, а раскладка (строки и колонки)
    вычисляется методом :meth:`get_rows`.

    Attributes:
        buttons: Кнопки в порядке добавления.
        one_time: Прятать клавиатуру после нажатия (где платформа поддерживает).
        resize: Автоматически уменьшать клавиатуру (Telegram; VK игнорирует).
        inline: Inline-клавиатура (под сообщением) вместо клавиатуры ввода.
    """

    buttons: list[Button] = field(default_factory=list)
    one_time: bool = False
    resize: bool = True
    inline: bool = False

    def add(self, button: Button) -> Keyboard:
        """Добавляет кнопку в конец клавиатуры.

        Args:
            button: Кнопка в абстрактном формате.

        Returns:
            Та же клавиатура (для цепочки вызовов).

        Raises:
            ValueError: если передан не объект :class:`Button`.
        """
        if not isinstance(button, Button):
            raise ValueError(
                f"Ожидается объект Button, получен: {type(button).__name__}"
            )
        self.buttons.append(button)
        return self

    def __len__(self) -> int:
        """Возвращает количество кнопок в клавиатуре."""
        return len(self.buttons)

    def get_rows(self) -> list[list[Button]]:
        """Раскладывает кнопки по строкам и колонкам.

        Правила раскладки:

        * кнопки с явными ``row``/``column`` встают по указанным позициям;
        * кнопки без ``row`` получают каждая по отдельной новой строке
          ниже всех явно заданных (в порядке добавления);
        * кнопки без ``column`` идут после кнопок с явной колонкой
          (в порядке добавления);
        * пропущенные номера строк заполняются пустыми строками;
        * пропуски в нумерации колонок не сохраняются — внутри строки
          кнопки всегда идут подряд слева направо.

        Returns:
            Список строк: каждая строка — список кнопок слева направо.
        """
        grouped: dict[int, list[tuple[int, Button]]] = {}
        auto: list[tuple[int, Button]] = []
        for index, button in enumerate(self.buttons):
            if button.row is None:
                auto.append((index, button))
            else:
                grouped.setdefault(button.row, []).append((index, button))

        # Кнопки без явной строки — каждая в новую строку ниже всех явных
        next_row = max(grouped, default=-1) + 1
        for item in auto:
            grouped.setdefault(next_row, []).append(item)
            next_row += 1

        if not grouped:
            return []

        def sort_key(item: tuple[int, Button]) -> tuple[int, int]:
            """Сортирует кнопки строки: явные колонки слева, затем остальные."""
            index, button = item
            if button.column is None:
                return (1, index)
            return (0, button.column)

        rows: list[list[Button]] = []
        for row_index in range(max(grouped) + 1):
            items = sorted(grouped.get(row_index, []), key=sort_key)
            rows.append([button for _, button in items])
        return rows

    def row_count(self) -> int:
        """Возвращает количество строк с учётом автоматической раскладки.

        Returns:
            Число строк (0 — пустая клавиатура).
        """
        return len(self.get_rows())

    def buttons_at(self, row: int) -> list[Button]:
        """Возвращает кнопки одной строки слева направо.

        Args:
            row: Номер строки (с нуля).

        Returns:
            Список кнопок; пустой, если строки не существует.
        """
        rows = self.get_rows()
        if 0 <= row < len(rows):
            return list(rows[row])
        return []

    def buttons_in_column(self, column: int) -> list[Button]:
        """Возвращает кнопки заданной колонки сверху вниз.

        Args:
            column: Номер колонки (с нуля).

        Returns:
            Кнопки, у которых задан ``column`` с этим номером (кнопки
            без явной колонки не входят).
        """
        return [
            button
            for row in self.get_rows()
            for button in row
            if button.column == column
        ]


__all__ = ("Button", "ButtonColor", "ButtonType", "Keyboard")
