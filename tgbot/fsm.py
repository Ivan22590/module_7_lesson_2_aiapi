"""Адаптер хранения состояний для Telegram-бота (aiogram).

Тонкий слой между общим ``common.fsm.States`` (и
``common.context.ChatContextStore``) и обработчиками aiogram:

* middleware добавляет в контекст обработчика ``states``, ``context``
  и ``user_id`` — обработчик объявляет их параметрами с дефолтами;
* фильтры :func:`state_is` и :func:`state_is_none` сопоставляют событие
  с текущим состоянием пользователя.

Пример:
    >>> from tgbot import Router, state_is
    >>> from common.fsm import States
    >>> from common.storage import MemoryStorage
    >>> states = States(MemoryStorage())
    >>> router = Router()
    >>> @router.message(filt=state_is(states, "Menu:open"))
    ... async def handle_menu(message, bot=None, states=None, user_id=None):
    ...     states.reset(user_id)

Модуль не импортирует aiogram: фильтрам достаточно события с атрибутом
``from_user`` (``Message``, ``CallbackQuery`` и т.п.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from common.context import ChatContextStore
    from common.fsm import States

    from .filters import Filter

logger = logging.getLogger(__name__)

#: Имена, под которыми объекты состояний попадают в контекст обработчика
STATE_DATA_KEY: str = "states"
CONTEXT_DATA_KEY: str = "context"
USER_ID_DATA_KEY: str = "user_id"

#: Поля Update, внутри которых лежит событие с отправителем
_UPDATE_EVENT_FIELDS: tuple[str, ...] = (
    "message",
    "edited_message",
    "callback_query",
    "channel_post",
    "edited_channel_post",
    "inline_query",
    "chosen_inline_result",
    "shipping_query",
    "pre_checkout_query",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "business_message",
    "edited_business_message",
)


def extract_user_id(event: Any) -> int | None:
    """Возвращает идентификатор пользователя из события aiogram.

    Понимает и события уровня хендлера (``Message``, ``CallbackQuery``),
    и объект ``Update`` целиком (так приходит событие в update-level
    middleware).

    Args:
        event: Событие (``Message``, ``CallbackQuery``, ``Update``...).

    Returns:
        ``user_id`` или ``None``, если у события нет отправителя.
    """
    user = getattr(event, "from_user", None)
    if user is None:
        for field in _UPDATE_EVENT_FIELDS:
            sub_event = getattr(event, field, None)
            if sub_event is None:
                continue
            user = getattr(sub_event, "from_user", None)
            if user is not None:
                break
    user_id = getattr(user, "id", None)
    return int(user_id) if user_id is not None else None


def _resolve_user_id(event: Any, data: dict[str, Any]) -> int | None:
    """Определяет user_id для middleware: контекст aiogram либо извлечение.

    Args:
        event: Событие (на update-уровне — объект ``Update``).
        data: Контекстные данные aiogram (заполняет UserContextMiddleware,
            который отрабатывает раньше нашего слоя).

    Returns:
        ``user_id`` события или ``None``.
    """
    event_context = data.get("event_context")
    context_user_id = getattr(event_context, "user_id", None)
    if context_user_id is not None:
        return int(context_user_id)
    return extract_user_id(event)


def make_states_middleware(
    states: "States",
    context: "ChatContextStore | None" = None,
) -> Callable[..., Any]:
    """Создаёт outer-middleware, инъецирующее состояния в обработчики.

    Middleware кладёт в контекст aiogram три значения:

    * ``states`` — объект :class:`common.fsm.States`;
    * ``context`` — объект :class:`common.context.ChatContextStore`
      (если передан);
    * ``user_id`` — идентификатор пользователя события (или ``None``).

    Обработчики получают их, объявив одноимённые параметры
    (с дефолтами ``None``).

    Args:
        states: Машина состояний поверх ``common.storage``.
        context: Хранилище истории диалога (опционально).

    Returns:
        Async-middleware для ``dispatcher.update.outer_middleware``.
    """

    async def middleware(handler: Any, event: Any, data: dict[str, Any]) -> Any:
        data[STATE_DATA_KEY] = states
        if context is not None:
            data[CONTEXT_DATA_KEY] = context
        data[USER_ID_DATA_KEY] = _resolve_user_id(event, data)
        return await handler(event, data)

    return middleware


def state_is(states: "States", *names: str) -> "Filter":
    """Фильтр: текущее состояние пользователя равно одному из ``names``.

    Используется как ``filt=`` при регистрации в
    :class:`tgbot.router.Router`::

        @router.message(filt=state_is(states, "Settings:waiting_input"))

    Args:
        states: Машина состояний (та же, что передана боту в ``states=``).
        *names: Имена состояний (строки).

    Returns:
        Предикат для фильтров роутера. Не срабатывает для событий
        без отправителя.
    """
    expected = frozenset(names)

    def check(event: Any) -> bool:
        user_id = extract_user_id(event)
        return user_id is not None and states.get_state(user_id) in expected

    return check


def state_is_none(states: "States") -> "Filter":
    """Фильтр: у пользователя нет активного состояния.

    Полезен, чтобы «обычный» обработчик не перехватывал пользователя,
    находящегося в середине многошагового сценария::

        @router.message(filt=state_is_none(states))
        async def handle_chat(message, bot=None, states=None, user_id=None): ...

    Args:
        states: Машина состояний (та же, что передана боту в ``states=``).

    Returns:
        Предикат для фильтров роутера. Не срабатывает для событий
        без отправителя.
    """

    def check(event: Any) -> bool:
        user_id = extract_user_id(event)
        return user_id is not None and states.get_state(user_id) is None

    return check


__all__ = (
    "extract_user_id",
    "make_states_middleware",
    "state_is",
    "state_is_none",
    "STATE_DATA_KEY",
    "CONTEXT_DATA_KEY",
    "USER_ID_DATA_KEY",
)
