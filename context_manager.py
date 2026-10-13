"""Менеджер контекста диалога — история реплик пользователя в памяти процесса.

Обёртка над ``common.context.ChatContextStore`` (поверх
``common.storage.MemoryStorage``): хранит историю «пользователь ↔ ассистент»
и отдельное системное сообщение для каждого пользователя.

Системное сообщение хранится **вне** истории, поэтому не отбрасывается при
обрезке старых реплик и всегда подставляется первым в запрос к модели.

Пример:
    >>> from context_manager import ContextManager
    >>> manager = ContextManager()
    >>> manager.set_system_message(42, "Отвечай кратко.")
    >>> manager.append_user(42, "Привет!")
    >>> manager.messages(42)
    [{'role': 'system', 'content': 'Отвечай кратко.'}, {'role': 'user', 'content': 'Привет!'}]
"""

from __future__ import annotations

import logging

from common.context import ChatContextStore
from common.storage import MemoryStorage

logger = logging.getLogger(__name__)


class ContextManager:
    """История диалога и системное сообщение на каждого пользователя.

    Args:
        max_messages: Сколько последних реплик (user/assistant) хранить.
        max_chars: Суммарный бюджет символов содержимого реплик.
    """

    def __init__(self, *, max_messages: int = 20, max_chars: int = 8000) -> None:
        self._storage = MemoryStorage()
        self._store = ChatContextStore(
            self._storage,
            max_messages=max_messages,
            max_chars=max_chars,
        )
        self._system: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Системное сообщение
    # ------------------------------------------------------------------

    def set_system_message(self, user_id: int, text: str) -> None:
        """Сохраняет системное сообщение пользователя (пусто — удаляет).

        Args:
            user_id: Идентификатор пользователя.
            text: Текст системной инструкции.
        """
        cleaned = (text or "").strip()
        if cleaned:
            self._system[user_id] = cleaned
        else:
            self._system.pop(user_id, None)
        logger.info(
            "Системное сообщение: user=%s len=%d", user_id, len(cleaned)
        )

    def get_system_message(self, user_id: int) -> str | None:
        """Возвращает системное сообщение пользователя или ``None``."""
        return self._system.get(user_id)

    # ------------------------------------------------------------------
    # История реплик
    # ------------------------------------------------------------------

    def append_user(self, user_id: int, text: str) -> None:
        """Добавляет реплику пользователя в историю."""
        self._store.append(user_id, "user", text)

    def append_assistant(self, user_id: int, text: str) -> None:
        """Добавляет ответ модели в историю."""
        self._store.append(user_id, "assistant", text)

    def messages(self, user_id: int) -> list[dict[str, str]]:
        """Возвращает сообщения для отправки в модель.

        Returns:
            Список ``{"role", "content"}``: системное сообщение (если задано)
            и история реплик.
        """
        messages: list[dict[str, str]] = []
        system = self._system.get(user_id)
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(self._store.history(user_id))
        return messages

    def size(self, user_id: int) -> int:
        """Возвращает число реплик истории пользователя (без system)."""
        return len(self._store.history(user_id))

    # ------------------------------------------------------------------
    # Очистка
    # ------------------------------------------------------------------

    def clear(self, user_id: int) -> None:
        """Удаляет историю диалога, системное сообщение сохраняет."""
        self._store.clear(user_id)
        logger.info("История очищена: user=%s", user_id)

    def reset(self, user_id: int) -> None:
        """Удаляет историю диалога и системное сообщение."""
        self._store.clear(user_id)
        self._system.pop(user_id, None)
        logger.info("Контекст сброшен полностью: user=%s", user_id)


__all__ = ("ContextManager",)
