"""Абстрактный интерфейс ключ-значение хранилища состояний.

Контракт один для всех бэкендов:

* ключ — непустая строка;
* значение — JSON-совместимый тип (``None``, ``bool``, ``int``, ``float``,
  ``str``, ``list``, ``dict``) — бэкенд можно менять без изменения
  потребителей;
* TTL (время жизни) — необязательный, в секундах, чистится лениво;
* ``keys(prefix)`` / ``clear(prefix)`` работают по префиксу ключей.

Операции синхронные и дешёвые (состояния ботов — маленькие данные).
«Тяжёлые» бэкенды (Redis, PostgreSQL) при появлении добавят свой адаптер.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

#: Версия формата данных на диске (для будущих миграций)
FORMAT_VERSION: int = 1


class StorageError(RuntimeError):
    """Ошибка хранилища (повреждённый файл, невалидные данные и т.п.)."""


def _validate_key(key: Any) -> None:
    """Проверяет, что ключ — непустая строка.

    Args:
        key: Проверяемый ключ.

    Raises:
        ValueError: если ключ не является непустой строкой.
    """
    if not isinstance(key, str) or not key:
        raise ValueError("Ключ хранилища должен быть непустой строкой")


def _validate_value(value: Any) -> None:
    """Проверяет, что значение сериализуется в JSON.

    Args:
        value: Проверяемое значение.

    Raises:
        StorageError: если значение не сериализуется в JSON.
    """
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise StorageError(
            "Значение не сериализуется в JSON "
            "(допустимы None, bool, int, float, str, list, dict): "
            f"{type(value).__name__}"
        ) from exc


def _make_record(value: Any, ttl: float | None) -> dict[str, Any]:
    """Создаёт внутреннюю запись хранилища «значение + срок годности».

    Args:
        value: Значение (уже проверенное).
        ttl: Время жизни в секундах; ``None`` — бессрочно.

    Returns:
        Словарь ``{"value": ..., "expires_at": ...}``.
    """
    expires_at = time.time() + ttl if ttl else None
    return {"value": value, "expires_at": expires_at}


def _is_expired(record: dict[str, Any]) -> bool:
    """Проверяет, истёк ли срок годности внутренней записи.

    Args:
        record: Внутренняя запись ``{"value", "expires_at"}``.

    Returns:
        ``True``, если запись истекла.
    """
    expires_at = record.get("expires_at")
    return expires_at is not None and time.time() >= expires_at


class Storage(ABC):
    """Ключ-значение хранилище с TTL и префиксами ключей.

    Все реализации обязаны соблюдать один контракт валидации
    (непустой строковый ключ, JSON-совместимое значение), поэтому
    бэкенд переключается без изменения потребителей.
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает значение по ключу (с копией) или ``default``.

        Args:
            key: Ключ.
            default: Значение по умолчанию (отсутствие или истечение TTL).

        Returns:
            Копия сохранённого значения либо ``default``.
        """

    @abstractmethod
    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Сохраняет значение под ключом (перезаписывает).

        Args:
            key: Ключ.
            value: JSON-совместимое значение.
            ttl: Время жизни в секундах; ``None`` — бессрочно.

        Raises:
            ValueError: если ключ некорректен.
            StorageError: если значение не сериализуется в JSON.
        """

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Удаляет ключ.

        Args:
            key: Ключ.

        Returns:
            ``True``, если ключ существовал.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Проверяет наличие живого (неистёкшего) ключа.

        Args:
            key: Ключ.

        Returns:
            ``True``, если значение есть и не истекло.
        """

    @abstractmethod
    def keys(self, prefix: str = "") -> list[str]:
        """Возвращает отсортированные живые ключи (опционально по префиксу).

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.

        Returns:
            Список ключей по возрастанию.
        """

    @abstractmethod
    def clear(self, prefix: str = "") -> None:
        """Удаляет все ключи (опционально по префиксу).

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.
        """


__all__ = ("Storage", "StorageError", "FORMAT_VERSION")
