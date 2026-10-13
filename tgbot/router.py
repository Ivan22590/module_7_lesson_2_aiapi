"""Роутер Telegram-бота: реестр внешних обработчиков (поверх aiogram).

Роутер отделяет инфраструктуру бота от бизнес-логики: внешний проект
регистрирует свои команды, сообщения и callback-кнопки, а модуль ``/tgbot``
не знает, что именно они делают (в том числе — вызывать ли нейросеть).

Пример:
    >>> router = Router()
    >>> @router.command("start")
    ... async def start(message, bot=None):
    ...     await bot.send_message(message.chat.id, "Привет!")

Обработчики должны быть ``async``: aiogram работает на асинхронном
event loop, и синхронный обработчик не сможет отправлять сообщения
(регистрация такого обработчика сопровождается предупреждением в лог).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from .filters import Filter, any_text, callback_prefix, commands
from .types import Handler

logger = logging.getLogger(__name__)


def _command_filter(*names: str) -> Filter:
    """Фильтр команд, соответствующий прежнему поведению telebot.

    Срабатывает только на текстовые сообщения, начинающиеся со слэша
    (``/start``, ``/start@botname``) — как ``telebot.message_handler(commands=...)``.

    Args:
        *names: Имена команд без слэша.

    Returns:
        Предикат для проверки сообщения.
    """
    check_commands = commands(*names)

    def check(update: Any) -> bool:
        text = getattr(update, "text", None)
        if not isinstance(text, str) or not text.startswith("/"):
            return False
        return check_commands(update)

    return check


def _handler_params(handler: Handler) -> tuple[set[str], bool]:
    """Определяет, какие контекстные kwargs может получить обработчик.

    Первый позиционный параметр (событие) не входит в набор — он
    передаётся отдельно. Остальные имена берутся из контекста aiogram:
    ``bot``, ``states``, ``context``, ``user_id`` и т.д.

    Args:
        handler: Обработчик внешнего проекта.

    Returns:
        Кортеж «имена принимаемых kwargs, принимает ли ``**kwargs``».
        Для callable без разбираемой сигнатуры — параметр ``bot``.
    """
    try:
        parameters = inspect.signature(handler).parameters
    except (TypeError, ValueError):  # pragma: no cover - экзотические callable
        return {"bot"}, False

    names: set[str] = set()
    varkw = False
    first_positional_seen = False
    for param in parameters.values():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            if not first_positional_seen:
                first_positional_seen = True  # событие — не форвардим
                continue
            names.add(param.name)
        elif param.kind is inspect.Parameter.KEYWORD_ONLY:
            names.add(param.name)
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            varkw = True
    return names, varkw


@dataclass
class _Registration:
    """Одна запись реестра: способ регистрации и обработчик.

    Attributes:
        kind: Вид регистрации (``command`` / ``message`` / ``callback``).
        names: Имена команд (для ``command``).
        filt: Predicate для сообщений/кнопок.
        handler: Обработчик (async-функция).
    """

    kind: str
    handler: Handler
    names: tuple[str, ...] = ()
    filt: Filter | None = None


@dataclass
class Router:
    """Реестр обработчиков, применяемый к ``aiogram.Dispatcher`` при запуске.

    Поддерживаются три вида регистрации (в таком порядке они и применяются):
    команды → callback-кнопки → сообщения. Благодаря этому echo-обработчик
    по умолчанию не перехватывает команды.
    """

    _items: list[_Registration] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Регистрация обработчиков
    # ------------------------------------------------------------------

    def command(self, *names: str, handler: Handler | None = None) -> Any:
        """Регистрирует обработчик команды (``/start``, ``/help`` ...).

        Используется и как декоратор (``@router.command("start")``),
        и как обычный вызов (``router.command("start", handler=fn)``).

        Args:
            *names: Имена команд без слэша.
            handler: Async-обработчик. Если ``None`` — метод работает
                как декоратор.

        Returns:
            Обработчик либо декоратор.
        """
        if not names:
            raise ValueError("Не указано ни одной команды")

        def decorate(func: Handler) -> Handler:
            self._items.append(
                _Registration(kind="command", handler=func, names=tuple(names))
            )
            logger.debug("Зарегистрирована команда %s → %s", names, func.__name__)
            return func

        return decorate if handler is None else decorate(handler)

    def message(
        self,
        handler: Handler | None = None,
        *,
        filt: Filter | None = None,
    ) -> Any:
        """Регистрирует обработчик текстового сообщения.

        Args:
            handler: Async-обработчик (или ``None`` — использовать как декоратор).
            filt: Дополнительный предикат поверх текстового сообщения.
                ``None`` означает «любое текстовое сообщение».

        Returns:
            Обработчик либо декоратор.
        """

        def decorate(func: Handler) -> Handler:
            self._items.append(
                _Registration(kind="message", handler=func, filt=filt)
            )
            logger.debug("Зарегистрирован обработчик сообщений → %s", func.__name__)
            return func

        return decorate if handler is None else decorate(handler)

    def callback(
        self,
        handler: Handler | None = None,
        *,
        prefix: str | None = None,
        filt: Filter | None = None,
    ) -> Any:
        """Регистрирует обработчик нажатия inline-кнопки.

        Args:
            handler: Async-обработчик (или ``None`` — использовать как декоратор).
            prefix: Префикс ``data`` кнопки (например ``"menu:"``).
            filt: Свой предикат (если задан, ``prefix`` игнорируется).

        Returns:
            Обработчик либо декоратор.
        """
        chosen = filt if filt is not None else (
            callback_prefix(prefix) if prefix else None
        )

        def decorate(func: Handler) -> Handler:
            self._items.append(
                _Registration(kind="callback", handler=func, filt=chosen)
            )
            logger.debug("Зарегистрирован обработчик кнопок → %s", func.__name__)
            return func

        return decorate if handler is None else decorate(handler)

    def include(self, *initializers: Any) -> "Router":
        """Подключает внешние наборы обработчиков.

        Args:
            *initializers: Функции вида ``fn(router)``, которые регистрируют
                свои обработчики, или объекты с методом ``register(router)``.

        Returns:
            Тот же роутер (для цепочки вызовов).
        """
        for item in initializers:
            if hasattr(item, "register"):
                item.register(self)
            elif callable(item):
                item(self)
            else:
                raise TypeError(
                    f"Не удалось подключить {type(item).__name__}: "
                    "нужна функция или объект с методом register()"
                )
        return self

    # ------------------------------------------------------------------
    # Применение к диспетчеру aiogram
    # ------------------------------------------------------------------

    def register(self, dispatcher: Any, bot: Any) -> None:
        """Создаёт aiogram-роутер и подключает все обработчики к диспетчеру.

        Порядок важен: сначала команды, затем callback-кнопки, затем
        сообщения — в таком порядке aiogram проверяет обработчики.

        Args:
            dispatcher: Экземпляр ``aiogram.Dispatcher``.
            bot: Экземпляр ``aiogram.Bot`` — биндится в обработчики и
                передаётся внешним обработчикам в kwarg ``bot``.
        """
        from aiogram import F
        from aiogram import Router as AiogramRouter

        ai_router = AiogramRouter()

        for item in self._commands():
            ai_router.message.register(
                self._make_adapter(item.handler, bot),
                _command_filter(*item.names),
            )

        for item in self._callbacks():
            adapter = self._make_adapter(item.handler, bot)
            if item.filt is not None:
                ai_router.callback_query.register(adapter, item.filt)
            else:
                ai_router.callback_query.register(adapter)

        for item in self._messages():
            event_filters: list[Any] = [F.text]
            if item.filt is not None:
                event_filters.append(item.filt)
            ai_router.message.register(
                self._make_adapter(item.handler, bot), *event_filters
            )

        dispatcher.include_router(ai_router)
        logger.debug("В aiogram-роутер зарегистрировано записей: %d", len(self._items))

    def _make_adapter(self, handler: Handler, bot: Any) -> Handler:
        """Оборачивает обработчик внешнего проекта для передачи в aiogram.

        aiogram вызывает обработчик с объектом события первым аргументом
        и передаёт контекстные данные (``bot``, ``states``, ``context``,
        ``user_id``...) kwargs'ами. Обёртка отфильтровывает их по сигнатуре
        внешнего обработчика, поэтому тому достаточно объявить нужные
        параметры с дефолтами — без знания внутренностей aiogram.

        Args:
            handler: Обработчик внешнего проекта (async или sync).
            bot: Экземпляр ``aiogram.Bot`` — fallback для kwarg ``bot``.

        Returns:
            Async-функция с сигнатурой ``(event, **kwargs)`` для aiogram.
        """
        if not inspect.iscoroutinefunction(handler):
            logger.warning(
                "Обработчик %s синхронный: aiogram выполняет обработчики "
                "асинхронно — преобразуйте его в async def, иначе бот не "
                "сможет отправлять сообщения",
                getattr(handler, "__name__", handler),
            )

        accepted, accepts_varkw = _handler_params(handler)

        async def adapter(event: Any, **kwargs: Any) -> Any:
            if accepts_varkw:
                call_kwargs = dict(kwargs)
            else:
                call_kwargs = {
                    key: value for key, value in kwargs.items() if key in accepted
                }
            # Бот биндится при регистрации: работает и без bot в контексте
            if accepts_varkw or "bot" in accepted:
                call_kwargs.setdefault("bot", bot)
            result = handler(event, **call_kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        # Имя копируется без __wrapped__: aiogram определяет способ запуска
        # обёртки по исходной функции, и с __wrapped__ sync-обработчик
        # сломал бы выполнение async-обёртки.
        adapter.__name__ = getattr(handler, "__name__", "handler")
        adapter.__qualname__ = adapter.__name__
        adapter.__doc__ = getattr(handler, "__doc__", None)
        return adapter

    def _commands(self) -> Iterable[_Registration]:
        """Возвращает записи-команды в порядке регистрации."""
        return (item for item in self._items if item.kind == "command")

    def _callbacks(self) -> Iterable[_Registration]:
        """Возвращает записи callback-кнопок в порядке регистрации."""
        return (item for item in self._items if item.kind == "callback")

    def _messages(self) -> Iterable[_Registration]:
        """Возвращает записи сообщений в порядке регистрации."""
        return (item for item in self._items if item.kind == "message")

    @property
    def default_message_filter(self) -> Filter:
        """Предикат «любое текстовое сообщение» (используется служебными хендлерами)."""
        return any_text


__all__ = ("Router",)
