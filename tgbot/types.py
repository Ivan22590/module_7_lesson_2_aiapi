"""Служебные типы модуля ``/tgbot``.

Типы описывают контракты между роутером, обработчиками и промежуточными
слоями, чтобы внешний проект мог подключать свои обработчики без
знакомства с внутренним устройством модуля.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - типы нужны только для статической проверки
    from .router import Router

#: Обработчик сообщения/кнопки: async-функция, принимающая объект aiogram
#: и необязательный kwarg ``bot``
Handler = Callable[..., Any]

#: Функция, регистрирующая внешние обработчики в роутере
RouterInitializer = Callable[["Router"], None]  # noqa: F821 - имя строкой


@runtime_checkable
class SupportsRegister(Protocol):
    """Протокол объекта, умеющего регистрировать обработчики в роутере."""

    def register(self, router: Any) -> None:
        """Регистрирует обработчики в переданном роутере."""
        ...


def bot_type() -> Any:
    """Возвращает класс ``aiogram.Bot`` (для подсказок типов и проверок).

    Returns:
        Класс ``aiogram.Bot`` или ``None``, если aiogram не установлен.
    """
    try:
        import aiogram

        return aiogram.Bot
    except ImportError:  # pragma: no cover - зависимость обязательна в .venv
        return None


__all__ = ("Handler", "RouterInitializer", "SupportsRegister", "bot_type")
