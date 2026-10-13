"""История диалога с нейросетью (контекст на пользователя/чат).

Хранит последние реплики диалога «пользователь ↔ нейросеть» поверх
``common.storage`` и отдаёт их в формате, который напрямую принимает
``llm.LLMClient.chat`` — список словарей ``{"role", "content"}``.

История ограничивается по числу реплик и по суммарному бюджету символов:
старые реплики отбрасываются, поэтому запрос к модели не растёт бесконечно.

Пример:
    >>> from common.context import ChatContextStore
    >>> from common.storage import MemoryStorage
    >>> context = ChatContextStore(MemoryStorage())
    >>> context.append(42, "user", "Привет!")
    >>> context.history(42)
    [{'role': 'user', 'content': 'Привет!'}]
"""

from __future__ import annotations

from .storage import Storage

#: Префикс ключей истории по умолчанию (внутри общего хранилища)
DEFAULT_CONTEXT_PREFIX: str = "llm:ctx:"
#: Сколько последних реплик хранить по умолчанию
DEFAULT_MAX_MESSAGES: int = 20
#: Суммарный бюджет символов содержимого реплик по умолчанию
DEFAULT_MAX_CHARS: int = 8000

#: Допустимые роли реплик (контракт OpenAI-совместимых API)
ALLOWED_ROLES: tuple[str, ...] = ("system", "user", "assistant")


class ChatContextStore:
    """История диалога «пользователь ↔ нейросеть» поверх Storage.

    Args:
        storage: Любое хранилище ``common.storage.Storage``.
        key_prefix: Префикс ключей — позволяет держать несколько
            «пространств» в одном хранилище.
        max_messages: Сколько последних реплик хранить (``None``/``0`` — без
            ограничения по числу; ограничение по символам остаётся).
        max_chars: Суммарный бюджет символов содержимого; старые реплики
            отбрасываются, пока бюджет не будет соблюдён (минимум одна
            реплика сохраняется всегда).
    """

    def __init__(
        self,
        storage: Storage,
        *,
        key_prefix: str = DEFAULT_CONTEXT_PREFIX,
        max_messages: int | None = DEFAULT_MAX_MESSAGES,
        max_chars: int | None = DEFAULT_MAX_CHARS,
    ) -> None:
        self._storage = storage
        self._prefix = key_prefix
        self._max_messages = max(0, max_messages or 0)
        self._max_chars = max_chars

    # ------------------------------------------------------------------
    # Внутренние helpers
    # ------------------------------------------------------------------

    def _key(self, chat_id: int | str) -> str:
        """Собирает ключ хранилища для чата.

        Args:
            chat_id: Идентификатор чата (или пользователя).

        Returns:
            Ключ вида ``<prefix><chat_id>``.
        """
        return f"{self._prefix}{chat_id}"

    def _load(self, chat_id: int | str) -> list[dict[str, str]]:
        """Читает историю чата, отбрасывая повреждённые записи.

        Args:
            chat_id: Идентификатор чата.

        Returns:
            Список реплик ``{"role", "content"}``.
        """
        raw = self._storage.get(self._key(chat_id))
        if not isinstance(raw, list):
            return []
        history: list[dict[str, str]] = []
        for item in raw:
            if (
                isinstance(item, dict)
                and isinstance(item.get("role"), str)
                and isinstance(item.get("content"), str)
            ):
                history.append({"role": item["role"], "content": item["content"]})
        return history

    def _trim(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        """Обрезает историю по числу реплик и бюджету символов.

        Args:
            history: Исходная история (старые реплики в начале).

        Returns:
            История, укладывающаяся в лимиты (минимум одна реплика).
        """
        if self._max_messages and len(history) > self._max_messages:
            history = history[-self._max_messages:]
        if self._max_chars:
            while len(history) > 1:
                total = sum(len(item["content"]) for item in history)
                if total <= self._max_chars:
                    break
                history.pop(0)
        return history

    # ------------------------------------------------------------------
    # Публичный интерфейс
    # ------------------------------------------------------------------

    def append(self, chat_id: int | str, role: str, content: str) -> None:
        """Добавляет реплику в конец истории чата.

        Args:
            chat_id: Идентификатор чата.
            role: Роль реплики (``system`` / ``user`` / ``assistant``).
            content: Текст реплики.

        Raises:
            ValueError: если роль или текст пустые/нестроковые.
        """
        if not isinstance(role, str) or role not in ALLOWED_ROLES:
            raise ValueError(
                f"Роль реплики должна быть одной из {ALLOWED_ROLES}, получено: {role!r}"
            )
        if not isinstance(content, str) or not content:
            raise ValueError("Текст реплики должен быть непустой строкой")
        history = self._load(chat_id)
        history.append({"role": role, "content": content})
        self._storage.set(self._key(chat_id), self._trim(history))

    def history(self, chat_id: int | str) -> list[dict[str, str]]:
        """Возвращает историю чата в формате ``llm.LLMClient.chat``.

        Args:
            chat_id: Идентификатор чата.

        Returns:
            Копия списка реплик ``{"role", "content"}``.
        """
        return [dict(item) for item in self._load(chat_id)]

    def clear(self, chat_id: int | str) -> None:
        """Удаляет историю чата.

        Args:
            chat_id: Идентификатор чата.
        """
        self._storage.delete(self._key(chat_id))

    def __len__(self) -> int:  # pragma: no cover - не используется ботами
        """Возвращает число ключей-историй в хранилище.

        Returns:
            Количество чатов с сохранённой историей.
        """
        return len(self._storage.keys(self._prefix))


__all__ = (
    "ChatContextStore",
    "ALLOWED_ROLES",
    "DEFAULT_CONTEXT_PREFIX",
    "DEFAULT_MAX_MESSAGES",
    "DEFAULT_MAX_CHARS",
)
