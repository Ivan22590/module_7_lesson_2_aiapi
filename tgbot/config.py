"""Конфигурация Telegram-бота.

Единственная обязательная переменная окружения — ``TG_BOT_API_KEY``
(токен бота от @BotFather). Остальные параметры имеют значения
по умолчанию и не требуют ручной настройки.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Имена переменных окружения
ENV_BOT_TOKEN: str = "TG_BOT_API_KEY"
ENV_PARSE_MODE: str = "TG_BOT_PARSE_MODE"
ENV_POLLING_TIMEOUT: str = "TG_POLLING_TIMEOUT"

#: Режим разметки по умолчанию (HTML устойчив к неэкранированным символам)
DEFAULT_PARSE_MODE: str = "HTML"
#: Таймаут long-polling, секунды
DEFAULT_POLLING_TIMEOUT: int = 30

#: Типы апдейтов, которые бот обязан получать.
#:
#: Указаны явно и неизменно: Telegram запоминает последнюю заданную настройку
#: ``allowed_updates``. При передаче ``None`` сервер продолжает применять
#: старую, и если в ней нет ``callback_query``, inline-кнопки молча перестают
#: доходить до бота (сообщения приходят, нажатия — нет).
DEFAULT_ALLOWED_UPDATES: tuple[str, ...] = (
    "message",
    "edited_message",
    "callback_query",
    "inline_query",
)


class ConfigError(RuntimeError):
    """Ошибка конфигурации бота (отсутствует или пуст обязательный параметр)."""


def _load_env_file() -> None:
    """Загружает ``.env`` в окружение процесса.

    Ищет файл в каталоге модуля и далее в родительских каталогах (до трёх
    уровней вверх), поэтому модуль работает и в составе этого проекта,
    и скопированным в отдельный репозиторий.
    """
    current = Path(__file__).resolve().parent
    for _ in range(4):
        candidate = current / ".env"
        if candidate.is_file():
            load_dotenv(candidate)
            return
        if current.parent == current:
            break
        current = current.parent


def _read_timeout(default: int) -> int:
    """Читает таймаут polling из окружения, игнорируя некорректные значения.

    Args:
        default: Значение по умолчанию.

    Returns:
        Таймаут в секундах.
    """
    raw = os.getenv(ENV_POLLING_TIMEOUT, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class TelegramConfig:
    """Неизменяемая конфигурация Telegram-бота.

    Attributes:
        token: Токен бота (единственный секретный параметр модуля).
        parse_mode: Режим разметки сообщений (``HTML`` или ``Markdown``).
        allowed_updates: Типы апдейтов, запрашиваемых при polling.
        polling_timeout: Таймаут long-polling в секундах.
    """

    token: str
    parse_mode: str = DEFAULT_PARSE_MODE
    allowed_updates: tuple[str, ...] = field(default=DEFAULT_ALLOWED_UPDATES)
    polling_timeout: int = DEFAULT_POLLING_TIMEOUT

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        """Создаёт конфигурацию из переменных окружения (и ``.env``).

        Returns:
            Конфигурация бота; обязателен только токен.

        Raises:
            ConfigError: если ``TG_BOT_API_KEY`` отсутствует или пуста.
        """
        _load_env_file()

        token = os.getenv(ENV_BOT_TOKEN, "").strip()
        if not token:
            raise ConfigError(
                f"Не задана переменная окружения {ENV_BOT_TOKEN}. "
                f"Добавьте в файл .env строку: {ENV_BOT_TOKEN}=токен_бота"
            )

        return cls(
            token=token,
            parse_mode=os.getenv(ENV_PARSE_MODE, "").strip() or DEFAULT_PARSE_MODE,
            polling_timeout=_read_timeout(DEFAULT_POLLING_TIMEOUT),
        )


__all__ = (
    "TelegramConfig",
    "ConfigError",
    "DEFAULT_ALLOWED_UPDATES",
    "DEFAULT_PARSE_MODE",
    "DEFAULT_POLLING_TIMEOUT",
    "ENV_BOT_TOKEN",
)
