"""Основной файл Telegram-бота с контекстом LLM.

Стек: aiogram + proxyapi (llm) + MemoryStorage (контекст в памяти).

Сценарий:
  /start  — пошаговый ввод параметров (запрос → температура → max_tokens → system),
            затем первый ответ модели + inline-клавиатура;
  Любой текст в режиме диалога → ответ модели с историей;
  Inline-кнопка «Очистить контекст» / команда /reset → очистка истории.

Файлы проекта:
  config.py     — параметры модели, FSM-состояния, тексты, клавиатуры;
  context_manager.py — менеджер истории (MemoryStorage + ChatContextStore);
  api_client.py — обёртка над LLMClient с логированием параметров.

Запуск:
    python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from aiogram import F
from aiogram.types import CallbackQuery, Message

from common.fsm import States
from common.logging_setup import setup_logging
from common.storage import MemoryStorage

from api_client import ApiClient, ApiError
from config import (
    ASK_MAX_TOKENS,
    ASK_QUERY,
    ASK_SETUP_AGAIN,
    ASK_SYSTEM,
    ASK_TEMPERATURE,
    CLEAR_OK,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ERROR_API,
    ERROR_NO_STATE,
    ERROR_NUM,
    INLINE_KEYBOARD,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_MESSAGES,
    MODEL,
    RESET_OK,
    S_CHAT,
    S_MAX_TOKENS,
    S_QUERY,
    S_SYSTEM,
    S_TEMPERATURE,
    SKIP_SYSTEM_KEYBOARD,
    WELCOME_TEXT,
)
from context_manager import ContextManager
from llm import LLMError
from tgbot import ConfigError, Router, TelegramBot, TelegramConfig, state_is
from tgbot.utils import safe_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _split_text(text: str, limit: int = 4000) -> list[str]:
    """Разбивает длинный текст на части по ``limit`` символов."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        # Ищем границу слова
        cut = text[:limit].rfind(" ")
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    return parts


# ---------------------------------------------------------------------------
# Построение роутера
# ---------------------------------------------------------------------------


def build_router(
    states: States,
    ctx: ContextManager,
    api: ApiClient,
) -> Router:
    """Создаёт роутер бота: FSM-сценарий, диалог, inline-кнопки.

    Args:
        states: Машина состояний (общая с ботом — см. ``TelegramBot(states=)``).
        ctx: Менеджер контекста диалога.
        api: Клиент LLM API.

    Returns:
        Роутер с обработчиками.
    """
    router = Router()

    # ===== Команды =====

    @router.command("start")
    async def cmd_start(message: Message, bot: Any, states: Any, user_id: int) -> None:
        """Запускает / сбрасывает пошаговую настройку."""
        states.reset(user_id)
        ctx.reset(user_id)
        await bot.send_message(message.chat.id, WELCOME_TEXT)

    @router.command("help")
    async def cmd_help(message: Message, bot: Any) -> None:
        """Справка."""
        await bot.send_message(
            message.chat.id,
            (
                "/start — начать/сбросить настройку запроса\n"
                "/reset — очистить историю диалога\n"
                "/help — эта справка\n\n"
                "В режиме диалога используйте inline-кнопки:\n"
                "🔄 Новый запрос — настроить параметры заново\n"
                "🧹 Очистить контекст — очистить историю"
            ),
        )

    @router.command("reset")
    async def cmd_reset(
        message: Message,
        bot: Any,
        states: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        """Очищает историю диалога и системное сообщение."""
        ctx.reset(user_id)
        states.reset(user_id)
        await bot.send_message(message.chat.id, RESET_OK)

    # ===== Пошаговый ввод параметров =====

    @router.message(state_is(states, S_QUERY))
    @safe_handler
    async def handle_query(
        message: Message,
        bot: Any,
        states: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        ctx.set_system_message(user_id, "")  # сброс предыдущего system
        states.update_data(user_id, query=text)
        logger.info("Введён запрос (user=%s): %s", user_id, text[:100])
        states.set_state(user_id, S_TEMPERATURE)
        await bot.send_message(message.chat.id, ASK_TEMPERATURE)

    @router.message(state_is(states, S_TEMPERATURE))
    @safe_handler
    async def handle_temperature(
        message: Message,
        bot: Any,
        states: Any,
        user_id: int,
    ) -> None:
        raw = (message.text or "").strip()
        try:
            temp = float(raw)
        except (ValueError, TypeError):
            await bot.send_message(message.chat.id, ERROR_NUM)
            return
        if temp < 0.0 or temp > 2.0:
            await bot.send_message(
                message.chat.id, "Температура должна быть в диапазоне 0.0–2.0."
            )
            return
        states.update_data(user_id, temperature=temp)
        logger.info("Введена температура (user=%s): %.2f", user_id, temp)
        states.set_state(user_id, S_MAX_TOKENS)
        await bot.send_message(message.chat.id, ASK_MAX_TOKENS)

    @router.message(state_is(states, S_MAX_TOKENS))
    @safe_handler
    async def handle_max_tokens(
        message: Message,
        bot: Any,
        states: Any,
        user_id: int,
    ) -> None:
        raw = (message.text or "").strip()
        try:
            max_tok = int(raw)
        except (ValueError, TypeError):
            await bot.send_message(message.chat.id, ERROR_NUM)
            return
        if max_tok < 1 or max_tok > 4000:
            await bot.send_message(
                message.chat.id, "max_tokens должен быть в диапазоне 1–4000."
            )
            return
        states.update_data(user_id, max_tokens=max_tok)
        logger.info("Введён max_tokens (user=%s): %d", user_id, max_tok)
        states.set_state(user_id, S_SYSTEM)
        await bot.send_message(
            message.chat.id, ASK_SYSTEM, reply_markup=SKIP_SYSTEM_KEYBOARD
        )

    @router.message(state_is(states, S_SYSTEM))
    @safe_handler
    async def handle_system(
        message: Message,
        bot: Any,
        states: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        sys_msg = (message.text or "").strip()
        states.update_data(user_id, system_message=sys_msg)
        logger.info("Введено системное сообщение (user=%s): %s", user_id, sys_msg[:100] or "(пусто)")
        states.set_state(user_id, S_CHAT)
        await _run_first_request(bot, states, ctx, api, user_id)

    @router.callback(state_is(states, S_SYSTEM), prefix="setup:skip_system")
    @safe_handler
    async def cb_skip_system(
        callback: CallbackQuery,
        bot: Any,
        states: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        states.update_data(user_id, system_message="")
        logger.info("Пропущено системное сообщение (user=%s)", user_id)
        states.set_state(user_id, S_CHAT)
        await callback.answer()
        await _run_first_request(bot, states, ctx, api, user_id)

    # ===== Callback-кнопки =====

    @router.callback(prefix="setup:again")
    @safe_handler
    async def cb_new_request(
        callback: CallbackQuery,
        bot: Any,
        states: Any,
        user_id: int,
    ) -> None:
        states.reset(user_id)
        await callback.answer()
        await bot.send_message(callback.message.chat.id, ASK_SETUP_AGAIN)

    @router.callback(prefix="ctx:clear")
    @safe_handler
    async def cb_clear(
        callback: CallbackQuery,
        bot: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        ctx.clear(user_id)
        await callback.answer("Контекст очищен")
        await bot.send_message(callback.message.chat.id, CLEAR_OK)

    # ===== Диалог =====

    @router.message(state_is(states, S_CHAT))
    @safe_handler
    async def handle_chat(
        message: Message,
        bot: Any,
        states: Any,
        ctx: ContextManager,
        user_id: int,
    ) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        data = states.get_data(user_id)
        temperature = data.get("temperature", DEFAULT_TEMPERATURE)
        max_tokens = data.get("max_tokens", DEFAULT_MAX_TOKENS)
        logger.info(
            "Диалог (user=%s): temp=%.2f max_tok=%d",
            user_id,
            temperature,
            max_tokens,
        )
        ctx.append_user(user_id, text)
        messages = ctx.messages(user_id)
        logger.info("Отправляем в модель (user=%s): %d сообщений", user_id, len(messages))

        try:
            result = await asyncio.to_thread(
                api.ask,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (ApiError, LLMError) as exc:
            logger.error("Ошибка в диалоге (user=%s): %s", user_id, exc)
            await bot.send_message(message.chat.id, ERROR_API)
            return

        cost = api.estimate_cost(result.usage)
        cost_str = api.format_cost(cost)
        usage_str = ""
        if result.usage:
            usage_str = (
                f"\n📊 Токены: {result.usage.get('prompt_tokens', '?')} prompt / "
                f"{result.usage.get('completion_tokens', '?')} completion"
            )

        ctx.append_assistant(user_id, result.content)

        # Отправляем ответ (возможно, разбиваем на части)
        parts = _split_text(result.content)
        for i, part in enumerate(parts):
            footer = f"{cost_str}{usage_str}"
            if i == 0:
                full = part + footer
            else:
                full = part
            await bot.send_message(message.chat.id, full, reply_markup=INLINE_KEYBOARD)

    # ===== Фоллбэк =====

    @router.message(state_is(states, None))
    async def handle_no_state(
        message: Message,
        bot: Any,
    ) -> None:
        await bot.send_message(message.chat.id, ERROR_NO_STATE)

    return router


# ---------------------------------------------------------------------------
# Выполнение первого запроса после настройки
# ---------------------------------------------------------------------------


async def _run_first_request(
    bot: Any,
    states: Any,
    ctx: ContextManager,
    api: ApiClient,
    user_id: int,
) -> None:
    """Выполняет первый запрос модели после завершения настройки параметров."""
    data = states.get_data(user_id)
    query = data.get("query", "")
    temperature = data.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = data.get("max_tokens", DEFAULT_MAX_TOKENS)
    sys_msg = data.get("system_message", "")

    if not query:
        await bot.send_message(user_id, ERROR_NO_STATE)
        return

    # Сохраняем системное сообщение
    ctx.set_system_message(user_id, sys_msg)

    # Формируем сообщения
    messages: list[dict[str, str]] = []
    if sys_msg:
        messages.append({"role": "system", "content": sys_msg})
    messages.append({"role": "user", "content": query})

    logger.info(
        "Первый запрос после настройки (user=%s): %d сообщений, temp=%.2f, max_tok=%d",
        user_id,
        len(messages),
        temperature,
        max_tokens,
    )

    try:
        result = await asyncio.to_thread(
            api.ask,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (ApiError, LLMError) as exc:
        logger.error("Ошибка первого запроса (user=%s): %s", user_id, exc)
        await bot.send_message(user_id, ERROR_API)
        return

    cost = api.estimate_cost(result.usage)
    cost_str = api.format_cost(cost)
    usage_str = ""
    if result.usage:
        usage_str = (
            f"\n📊 Токены: {result.usage.get('prompt_tokens', '?')} prompt / "
            f"{result.usage.get('completion_tokens', '?')} completion"
        )

    ctx.append_assistant(user_id, result.content)

    parts = _split_text(result.content)
    for i, part in enumerate(parts):
        footer = f"{cost_str}{usage_str}"
        full = part + footer if i == 0 else part
        await bot.send_message(user_id, full, reply_markup=INLINE_KEYBOARD)


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------


def main() -> None:
    """Настраивает логирование, создаёт компоненты и запускает бота."""
    setup_logging()

    try:
        config = TelegramConfig.from_env()
    except ConfigError as exc:
        logger.error("Ошибка конфигурации бота: %s", exc)
        raise

    storage = MemoryStorage()
    fsm_states = States(storage)
    ctx_manager = ContextManager(
        max_messages=MAX_CONTEXT_MESSAGES,
        max_chars=MAX_CONTEXT_CHARS,
    )
    api_client = ApiClient(
        model=MODEL,
        default_temperature=DEFAULT_TEMPERATURE,
        default_max_tokens=DEFAULT_MAX_TOKENS,
    )

    bot = TelegramBot(
        config=config,
        router=build_router(fsm_states, ctx_manager, api_client),
        states=fsm_states,
        context=ctx_manager,
    )

    logger.info("Бот запущен: модель=%s temp=%.2f max_tokens=%d", MODEL, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS)
    bot.run()


if __name__ == "__main__":
    main()
