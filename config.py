"""Конфигурация Telegram-бота с контекстом LLM.

Содержит:
- модель, дефолты temperature / max_tokens, тарифы ProxyAPI;
- имена FSM-состояний;
- тексты сообщений бота;
- inline-клавиатуры (aiogram).

Пример:
    >>> from config import DEFAULT_TEMPERATURE, INLINE_KEYBOARD
    >>> print(DEFAULT_TEMPERATURE)  # 0.7
"""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

# ---------------------------------------------------------------------------
# Параметры LLM
# ---------------------------------------------------------------------------

#: Модель ProxyAPI (поддерживает temperature и max_tokens)
MODEL: str = "openai/gpt-4.1-mini"

#: Температура генерации по умолчанию
DEFAULT_TEMPERATURE: float = 0.7

#: Максимальное число генерируемых токенов по умолчанию
DEFAULT_MAX_TOKENS: int = 1024

#: Лимит реплик в контексте
MAX_CONTEXT_MESSAGES: int = 20

#: Суммарный бюджет символов в контексте
MAX_CONTEXT_CHARS: int = 8000

# ---------------------------------------------------------------------------
# Тарифы ProxyAPI (руб. за 1 000 000 токенов)
# ---------------------------------------------------------------------------

#: Стоимость ввода на 1М токенов для указанной модели
PRICE_INPUT_PER_M: float = 104.0

#: Стоимость вывода на 1М токенов для указанной модели
PRICE_OUTPUT_PER_M: float = 413.0

# ---------------------------------------------------------------------------
# FSM-состояния
# ---------------------------------------------------------------------------

S_QUERY: str = "Setup:query"
S_TEMPERATURE: str = "Setup:temperature"
S_MAX_TOKENS: str = "Setup:max_tokens"
S_SYSTEM: str = "Setup:system"
S_CHAT: str = "Chat"

# ---------------------------------------------------------------------------
# Тексты сообщений
# ---------------------------------------------------------------------------

WELCOME_TEXT: str = (
    "Привет! Я бот с контекстом LLM.\n\n"
    "Сначала укажи параметры запроса — отправь *сообщение* с текстом "
    "для нейросети.\n\n"
    "Затем последовательно укажи:\n"
    "• температуру (по умолчанию 0.7);\n"
    "• max_tokens (по умолчанию 1024);\n"
    "• системное сообщение (опционально).\n\n"
    "После настройки будешь писать — я отвечу с учётом истории."
)

ASK_QUERY: str = "Отправь текст запроса для нейросети:"
ASK_TEMPERATURE: str = "Укажи температуру (float, 0.0–2.0). По умолчанию: 0.7\n(или просто отправь число)"
ASK_MAX_TOKENS: str = "Укажи max_tokens (int, 1–4000). По умолчанию: 1024\n(или просто отправь число)"
ASK_SYSTEM: str = "Отправь системное сообщение (опционально).\nМожно пропустить — нажми кнопку ниже."
ASK_SETUP_AGAIN: str = "Настрой параметры для нового запроса:\nотправь текст запроса для нейросети."
CLEAR_OK: str = "Контекст очищен. Отправь новый запрос или нажми «Новый запрос»."
RESET_OK: str = "История диалога и системное сообщение очищены. Начинай заново."
ERROR_NUM: str = "Пожалуйста, введите корректное число."
ERROR_TEMPERATURE: str = "Температура должна быть в диапазоне 0.0–2.0."
ERROR_MAX_TOKENS: str = "max_tokens должен быть в диапазоне 1–4000."
ERROR_NO_STATE: str = (
    "У бота нет активного состояния.\n"
    "Отправь /start чтобы начать новый запрос."
)
ERROR_API: str = "Ошибка обращения к нейросети. Попробуйте ещё раз."

HELP_TEXT: str = (
    "Команды:\n"
    "/start — начать/сбросить настройку запроса\n"
    "/reset — очистить историю диалога\n"
    "/help — эта справка\n\n"
    "В режиме диалога используйте inline-кнопки:\n"
    "🔄 Новый запрос — настроить параметры заново\n"
    "🧹 Очистить контекст — очистить историю"
)

# ---------------------------------------------------------------------------
# Inline-клавиатуры
# ---------------------------------------------------------------------------

#: Клавиатура в каждом ответе (после настройки): [Новый запрос | Очистить контекст]
INLINE_KEYBOARD: InlineKeyboardMarkup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Новый запрос", callback_data="setup:again"),
        ],
        [
            InlineKeyboardButton(text="🧹 Очистить контекст", callback_data="ctx:clear"),
        ],
    ]
)

#: Inline-кнопка «Пропустить» для шага системного сообщения
SKIP_SYSTEM_KEYBOARD: InlineKeyboardMarkup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="setup:skip_system"),
        ],
    ]
)

__all__ = (
    "MODEL",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_MAX_TOKENS",
    "MAX_CONTEXT_MESSAGES",
    "MAX_CONTEXT_CHARS",
    "PRICE_INPUT_PER_M",
    "PRICE_OUTPUT_PER_M",
    "S_QUERY",
    "S_TEMPERATURE",
    "S_MAX_TOKENS",
    "S_SYSTEM",
    "S_CHAT",
    "WELCOME_TEXT",
    "ASK_QUERY",
    "ASK_TEMPERATURE",
    "ASK_MAX_TOKENS",
    "ASK_SYSTEM",
    "ASK_SETUP_AGAIN",
    "CLEAR_OK",
    "RESET_OK",
    "ERROR_NUM",
    "ERROR_TEMPERATURE",
    "ERROR_MAX_TOKENS",
    "ERROR_NO_STATE",
    "ERROR_API",
    "HELP_TEXT",
    "INLINE_KEYBOARD",
    "SKIP_SYSTEM_KEYBOARD",
)
