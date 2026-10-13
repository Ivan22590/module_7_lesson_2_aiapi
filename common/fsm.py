"""Универсальная машина состояний (FSM) поверх ``common.storage``.

Хранит на каждого пользователя пару «имя состояния (строка) + данные шага
(словарь)». Имя состояния — произвольная строка: каждый бот мапит на неё
свои нативные состояния (vkbottle ``BaseStateGroup`` и т.п.), поэтому
абстракция одинаково работает в Telegram- и VK-боте.

Пример:
    >>> from common.fsm import States
    >>> from common.storage import MemoryStorage
    >>> states = States(MemoryStorage())
    >>> states.set_state(42, "Settings:waiting_input", reason="prompt")
    >>> states.get_state(42)
    'Settings:waiting_input'
    >>> states.get_data(42)
    {'reason': 'prompt'}
    >>> states.reset(42)
"""

from __future__ import annotations

from typing import Any

from .storage import Storage

#: Префикс ключей FSM по умолчанию (внутри общего хранилища)
DEFAULT_FSM_PREFIX: str = "fsm:"


class States:
    """Состояния и данные шагов диалога на пользователя.

    Args:
        storage: Любое хранилище ``common.storage.Storage``.
        key_prefix: Префикс ключей — позволяет держать несколько
            «пространств» состояний в одном хранилище.
        ttl: Время жизни записи в секундах (обновляется при каждой записи);
            ``None`` — бессрочно.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        key_prefix: str = DEFAULT_FSM_PREFIX,
        ttl: float | None = None,
    ) -> None:
        self._storage = storage
        self._prefix = key_prefix
        self._ttl = ttl

    # ------------------------------------------------------------------
    # Внутренние helpers
    # ------------------------------------------------------------------

    def _key(self, user_id: int | str) -> str:
        """Собирает ключ хранилища для пользователя.

        Args:
            user_id: Идентификатор пользователя (или чата).

        Returns:
            Ключ вида ``<prefix><user_id>``.
        """
        return f"{self._prefix}{user_id}"

    def _record(self, user_id: int | str) -> dict[str, Any]:
        """Читает «сырую» запись пользователя (или пустой словарь).

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Словарь ``{"state": ..., "data": {...}}``.
        """
        record = self._storage.get(self._key(user_id))
        if not isinstance(record, dict):
            return {}
        return record

    # ------------------------------------------------------------------
    # Состояние
    # ------------------------------------------------------------------

    def get_state(self, user_id: int | str) -> str | None:
        """Возвращает текущее имя состояния пользователя.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Имя состояния или ``None``, если состояния нет.
        """
        state = self._record(user_id).get("state")
        return state if isinstance(state, str) else None

    def set_state(
        self,
        user_id: int | str,
        state: str | None,
        *,
        ttl: float | None = None,
    ) -> None:
        """Устанавливает состояние пользователя (``None`` — снимает).

        Данные шага при смене состояния сохраняются; полная очистка —
        :meth:`reset`.

        Args:
            user_id: Идентификатор пользователя.
            state: Новое имя состояния или ``None``.
            ttl: Переопределить время жизни записи (иначе — из конструктора).

        Raises:
            ValueError: если имя состояния не непустая строка.
        """
        if state is not None and (not isinstance(state, str) or not state):
            raise ValueError("Имя состояния должно быть непустой строкой")
        record = self._record(user_id)
        record["state"] = state
        record.setdefault("data", {})
        self._storage.set(
            self._key(user_id), record, self._ttl if ttl is None else ttl
        )

    # ------------------------------------------------------------------
    # Данные шага
    # ------------------------------------------------------------------

    def get_data(self, user_id: int | str) -> dict[str, Any]:
        """Возвращает данные текущего шага диалога.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Копия словаря данных (пустой, если данных нет).
        """
        data = self._record(user_id).get("data")
        return dict(data) if isinstance(data, dict) else {}

    def update_data(
        self,
        user_id: int | str,
        *,
        ttl: float | None = None,
        **values: Any,
    ) -> dict[str, Any]:
        """Частично обновляет данные шага и возвращает их.

        Args:
            user_id: Идентификатор пользователя.
            ttl: Переопределить время жизни записи (иначе — из конструктора).
            **values: Новые значения (JSON-совместимые).

        Returns:
            Обновлённые данные шага.
        """
        record = self._record(user_id)
        data = record.get("data")
        merged = {**data, **values} if isinstance(data, dict) else dict(values)
        record["data"] = merged
        self._storage.set(
            self._key(user_id), record, self._ttl if ttl is None else ttl
        )
        return dict(merged)

    def reset(self, user_id: int | str) -> None:
        """Полностью очищает состояние и данные пользователя.

        Args:
            user_id: Идентификатор пользователя.
        """
        self._storage.delete(self._key(user_id))


__all__ = ("States", "DEFAULT_FSM_PREFIX")
