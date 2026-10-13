"""Персистентное хранилище состояний в JSON-файле."""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from .base import (
    FORMAT_VERSION,
    Storage,
    StorageError,
    _is_expired,
    _make_record,
    _validate_key,
    _validate_value,
)


class JsonFileStorage(Storage):
    """Хранилище с состоянием в JSON-файле (переживает перезапуск).

    Файл создаётся лениво при первом обращении; каждая запись сохраняется
    атомарно (через временный файл + ``os.replace``), поэтому сбой в момент
    записи не портит предыдущее состояние. Рассчитан на **один процесс**
    (типичный бот на polling): для нескольких процессов нужен другой бэкенд.

    Формат файла::

        {"version": 1, "entries": {"ключ": {"value": ..., "expires_at": ...}}}

    Пример:
        >>> storage = JsonFileStorage("state/bot_state.json")
        >>> storage.set("user:1", {"state": "menu"}, ttl=3600)
    """

    def __init__(self, path: str | Path) -> None:
        """Создаёт хранилище поверх указанного файла.

        Args:
            path: Путь к JSON-файлу (каталоги создаются автоматически).
        """
        self.path = Path(path)
        self._data: dict[str, Any] | None = None  # ленивая загрузка
        # Фильтры aiogram выполняются в отдельных потоках (to_thread) —
        # блокировка защищает от гонок при ленивой загрузке и записи
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Работа с файлом
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Загружает данные файла лениво (один раз на жизнь объекта).

        Returns:
            Словарь ``{"version": ..., "entries": {...}}``.

        Raises:
            StorageError: если файл отсутствует в ожидаемом формате
                или повреждён.
        """
        if self._data is not None:
            return self._data
        if not self.path.exists():
            self._data = {"version": FORMAT_VERSION, "entries": {}}
            return self._data
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(
                f"Не удалось прочитать файл состояний {self.path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
            raise StorageError(
                f"Файл состояний {self.path} повреждён: нет секции 'entries'"
            )
        self._data = raw
        return raw

    def _save(self) -> None:
        """Атомарно сохраняет данные на диск (временный файл + replace).

        Raises:
            StorageError: если запись на диск не удалась.
        """
        assert self._data is not None  # noqa: S101 - инвариант, _save зовут после _load
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, self.path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise StorageError(
                f"Не удалось записать файл состояний {self.path}: {exc}"
            ) from exc

    def _prune_expired(self) -> bool:
        """Удаляет истёкшие записи из памяти.

        Returns:
            ``True``, если что-то было удалено (нужна запись на диск).
        """
        entries: dict[str, Any] = self._load()["entries"]
        expired = [key for key, record in entries.items() if _is_expired(record)]
        for key in expired:
            entries.pop(key, None)
        return bool(expired)

    # ------------------------------------------------------------------
    # Интерфейс Storage
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает копию значения по ключу или ``default``.

        Истёкшие записи удаляются лениво (при обращении).

        Args:
            key: Ключ.
            default: Значение по умолчанию (отсутствие или истечение TTL).

        Returns:
            Копия сохранённого значения либо ``default``.
        """
        _validate_key(key)
        with self._lock:
            entries: dict[str, Any] = self._load()["entries"]
            record = entries.get(key)
            if record is None:
                return default
            if _is_expired(record):
                entries.pop(key, None)
                self._save()
                return default
            return copy.deepcopy(record["value"])

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Сохраняет значение под ключом и пишет файл.

        Args:
            key: Ключ (непустая строка).
            value: JSON-совместимое значение.
            ttl: Время жизни в секундах; ``None`` — бессрочно.

        Raises:
            ValueError: если ключ некорректен.
            StorageError: если значение не сериализуется или запись не удалась.
        """
        _validate_key(key)
        _validate_value(value)
        with self._lock:
            self._load()["entries"][key] = _make_record(value, ttl)
            self._save()

    def delete(self, key: str) -> bool:
        """Удаляет ключ и пишет файл.

        Args:
            key: Ключ.

        Returns:
            ``True``, если ключ существовал.
        """
        _validate_key(key)
        with self._lock:
            removed = self._load()["entries"].pop(key, None) is not None
            if removed:
                self._save()
            return removed

    def exists(self, key: str) -> bool:
        """Проверяет наличие живого (неистёкшего) ключа.

        Args:
            key: Ключ.

        Returns:
            ``True``, если значение есть и не истекло.
        """
        _validate_key(key)
        with self._lock:
            entries: dict[str, Any] = self._load()["entries"]
            record = entries.get(key)
            if record is None:
                return False
            if _is_expired(record):
                entries.pop(key, None)
                self._save()
                return False
            return True

    def keys(self, prefix: str = "") -> list[str]:
        """Возвращает отсортированные живые ключи (опционально по префиксу).

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.

        Returns:
            Список ключей по возрастанию.
        """
        with self._lock:
            if self._prune_expired():
                self._save()
            entries: dict[str, Any] = self._load()["entries"]
            return sorted(key for key in entries if key.startswith(prefix))

    def clear(self, prefix: str = "") -> None:
        """Удаляет все ключи (опционально по префиксу) и пишет файл.

        Args:
            prefix: Префикс ключей; ``""`` — все ключи.
        """
        with self._lock:
            entries: dict[str, Any] = self._load()["entries"]
            doomed = [key for key in entries if key.startswith(prefix)]
            for key in doomed:
                entries.pop(key, None)
            if doomed:
                self._save()


__all__ = ("JsonFileStorage",)
