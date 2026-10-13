"""Универсальное ключ-значение хранилище состояний.

Два готовых бэкенда с единым контрактом (см.
:class:`~common.storage.base.Storage`):

* :class:`~common.storage.memory.MemoryStorage` — в памяти процесса
  (тесты, демо, быстрый старт);
* :class:`~common.storage.json_file.JsonFileStorage` — в JSON-файле
  с атомарной записью (переживает перезапуск, без новых зависимостей).

Пример:
    >>> from common.storage import JsonFileStorage, MemoryStorage
    >>> storage = MemoryStorage()
    >>> storage.set("user:1", {"state": "menu"}, ttl=3600)
    >>> storage.get("user:1")
    {'state': 'menu'}

Над хранилищем построены: машина состояний :class:`common.fsm.States`
и история диалога с нейросетью :class:`common.context.ChatContextStore`.
"""

from __future__ import annotations

from .base import FORMAT_VERSION, Storage, StorageError
from .json_file import JsonFileStorage
from .memory import MemoryStorage

__all__ = (
    "Storage",
    "StorageError",
    "MemoryStorage",
    "JsonFileStorage",
    "FORMAT_VERSION",
)
