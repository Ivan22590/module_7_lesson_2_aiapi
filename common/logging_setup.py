"""Общая настройка логирования проекта.

Единственная точка настройки логирования для всех модулей: ``/llm``,
``/tgbot`` и ``/vkbot`` используют именованные логгеры (``logging.getLogger(__name__)``),
а формат и уровень задаются здесь.

Особенности:
    * уровень читается из переменной окружения ``LOG_LEVEL`` (по умолчанию ``INFO``);
    * логи пишутся и в stdout, и в файл ``logs/app.log`` (по умолчанию);
    * путь к файлу задаётся переменной ``LOG_FILE``, запись отключается
      значением ``LOG_FILE=-``;
    * собственные выводчики сторонних библиотек (vkbottle) отключаются,
      чтобы не дублировать записи;
    * в логи не должны попадать секреты (ключи, токены) — это ответственность
      вызывающего кода: сюда передаются только диагностические сообщения.

Пример:
    >>> from common.logging_setup import setup_logging
    >>> setup_logging()                 # консоль + logs/app.log
    >>> setup_logging(log_file="-")     # только консоль
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Значения по умолчанию
DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

#: Файл для записи логов по умолчанию (отключается через LOG_FILE=-)
DEFAULT_LOG_FILE: str = "logs/app.log"

#: Значения LOG_FILE, при которых запись в файл отключается
FILE_DISABLED_VALUES: frozenset[str] = frozenset(
    {"", "0", "no", "false", "нет", "off", "none", "-"}
)

# Библиотеки, которые добавляют собственные выводчики и дублируют записи
_THIRD_PARTY_LOGGERS: tuple[str, ...] = ("vkbottle",)

# Форматчик переиспользуется всеми обработчиками
_FORMATTER = logging.Formatter(DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)


def disable_third_party_handlers() -> None:
    """Отключает собственные выводчики сторонних библиотек.

    Некоторые библиотеки (например, vkbottle) добавляют свой
    ``StreamHandler`` в свои логгеры — из-за этого каждая запись
    дублируется: один раз в формате библиотеки и один раз в общем
    формате проекта. Эта функция снимает такие обработчики, оставляя
    запись через общий root-логгер (``propagate=True``).

    Вызывается автоматически из :func:`setup_logging`.
    """
    for name in _THIRD_PARTY_LOGGERS:
        library_logger = logging.getLogger(name)
        for handler in list(library_logger.handlers):
            library_logger.removeHandler(handler)
            handler.close()
        library_logger.propagate = True


def _resolve_level(level: str | None) -> int:
    """Преобразует имя уровня логирования в числовой уровень logging.

    Args:
        level: Имя уровня (``INFO``, ``debug`` и т.п.) или ``None`` — тогда
            берётся значение переменной окружения ``LOG_LEVEL``, а при её
            отсутствии — ``INFO``.

    Returns:
        Числовой уровень из модуля ``logging``.

    Примечание:
        Неизвестное имя уровня не приводит к ошибке — используется ``INFO``.
    """
    raw = (level or os.getenv("LOG_LEVEL") or DEFAULT_LOG_LEVEL).strip().upper()
    return getattr(logging, raw, logging.INFO)


def _resolve_file_path(log_file: str | Path | None) -> Path | None:
    """Определяет путь к файлу логов.

    Args:
        log_file: Явный путь (приоритет) либо ``None`` — тогда используется
            переменная окружения ``LOG_FILE``, а при её отсутствии — путь
            по умолчанию ``logs/app.log``.

    Returns:
        Путь к файлу логов или ``None``, если запись в файл отключена
        (значение из :data:`FILE_DISABLED_VALUES`, например ``LOG_FILE=-``).
    """
    if log_file is not None:
        text = str(log_file).strip()
        return None if text.lower() in FILE_DISABLED_VALUES else Path(text)

    env_value = os.getenv("LOG_FILE")
    if env_value is None:
        # LOG_FILE не задан — пишем в файл по умолчанию
        return Path(DEFAULT_LOG_FILE)
    text = env_value.strip()
    return None if text.lower() in FILE_DISABLED_VALUES else Path(text)


def setup_logging(
    level: str | None = None,
    log_file: str | Path | None = None,
) -> None:
    """Настраивает общий формат логирования для проекта.

    Корневой логгер очищается от старых обработчиков (защита от дублей
    при повторном вызове) и снабжается консольным и файловым обработчиками.
    Собственные выводчики сторонних библиотек (vkbottle) отключаются,
    чтобы записи не дублировались.

    Args:
        level: Уровень логирования (``DEBUG``, ``INFO``, ...). Если ``None``,
            берётся переменная окружения ``LOG_LEVEL`` (по умолчанию ``INFO``).
        log_file: Путь к файлу логов. Если ``None`` — берётся переменная
            окружения ``LOG_FILE``, а при её отсутствии используется
            ``logs/app.log``. Запись в файл отключается значением
            ``LOG_FILE=-`` (или явным ``log_file="-"``).

    Пример:
        >>> setup_logging()                        # консоль + logs/app.log
        >>> setup_logging(level="DEBUG")           # то же, но с уровнем DEBUG
        >>> setup_logging(log_file="-")            # только консоль
        >>> setup_logging(log_file="app.log")      # консоль + указанный файл
    """
    resolved_level = _resolve_level(level)

    root = logging.getLogger()
    root.setLevel(resolved_level)

    # Защита от дублирования обработчиков при повторной настройке
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    # Убираем собственные выводчики библиотек (иначе строки дублируются)
    disable_third_party_handlers()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(resolved_level)
    console.setFormatter(_FORMATTER)
    root.addHandler(console)

    # Запись в файл: по умолчанию включена, отключается через LOG_FILE=-
    path = _resolve_file_path(log_file)
    if path is not None:
        try:
            # Для простого имени файла parent == '.', mkdir в этом случае безопасен
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
        except OSError as exc:
            # Проблема с файлом не должна мешать работе приложения
            root.warning("Не удалось открыть файл логов %s: %s", path, exc)
        else:
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(_FORMATTER)
            root.addHandler(file_handler)


__all__ = (
    "setup_logging",
    "disable_third_party_handlers",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_FILE",
    "FILE_DISABLED_VALUES",
)
