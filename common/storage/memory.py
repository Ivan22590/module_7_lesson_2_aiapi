"""Хранилище состояний в памяти процесса."""

from __future__ import annotations

import copy
from typing import Any

from .base import Storage, _is_expired, _make_record, _validate_key, _validate_value


class MemoryStorage(Storage):
    """Хранилище в оперативной памяти (тесты, демо, быстрый старт).

    Данные не переживают перезапуск процесса — для персистентности
    используйте :class:`~common.storage.json_file.JsonFileStorage`.
    Значения возвращаются копиями, поэтому изменения снаружи не
    портят состояние хранилища.

    Пример:
        >>> storage = MemoryStorage()
        >>> storage.set("user:1", {"state": "menu"})
        >>> storage.get("user:1")
        {'state': 'menu'}
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает копию значения по ключу или ``default``.

        Args:
            key: Ключ.
            default: Значение по умолчанию (отсутствие или истечение TTL).

        Returns:
            Копия сохранённого значения либо ``default``.
        """
        _validate_key(key)
        record = self._records.get(key)
        if record is None:
            return default
        if _is_expired(record):
            self._records.pop(key, None)
            return default
        return copy.deepcopy(record["value"])

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Сохраняет значение под ключом (перезаписывает).

        Args:
            key: Ключ (непустая строка).
            value: JSON-совместимое значение.
            ttl: Время жизни в секундах; ``None`` — бессрочно.

        Raises:
            ValueError: если ключ некорректен.
            StorageError: если значение не сериализуется в JSON.
        """
        _validate_key(key)
        _validate_value(value)
        self._records[key] = _make_record(value, ttl)

    def delete(self, key: str) -> bool:
        """Удаляет ключ.

        Args:
            key: Ключ.

        Returns:
            ``True``, если ключ существовал.
        """
        _validate_key(key)
        return self._records.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        """Проверяет наличие живого (неистёкшего) ключа.

        Args:
            key: Ключ.

        Returns:
            ``True``, если значение есть и не истекло.
        """
        _validate_key(key)
        record = self._records.get(key)
        if record is None:
            return False
        if _is_expired(record):
            self._records.pop(key, None)
            return False
        return True

    def keys(self, prefix: str = "") -> list[str]:
        """Возвращает отсортированные живые ключи (опционально по префиксу).

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.

        Returns:
            Список ключей по возрастанию.
        """
        result: list[str] = []
        for key in sorted(self._records):  # копия списка — можно удалять в цикле
            if not key.startswith(prefix):
                continue
            if _is_expired(self._records[key]):
                self._records.pop(key, None)
                continue
            result.append(key)
        return result

    def clear(self, prefix: str = "") -> None:
        """Удаляет все ключи (опционально по префиксу).

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.
        """
        for key in self.keys(prefix):
            self._records.pop(key, None)


__all__ = ("MemoryStorage",)
