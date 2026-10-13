"""Основной файл Telegram-бота с контекстом LLM.

Стек: aiogram + ProxyAPI (``llm``) + контекст в памяти процесса.

Сценарий:
  /start  — пошаговый ввод параметров (запрос → температура → max_tokens → system),
            затем первый ответ модели + inline-клавиатура;
  любой текст в режиме диалога → ответ модели с учётом истории;
  inline-кнопка «Очистить контекст» / команда /reset → очистка истории.

Файлы проекта:
  config.py          — параметры модели, FSM-состояния, тексты, клавиатуры;
  context_manager.py — менеджер истории (MemoryStorage + ChatContextStore);
  api_client.py      — обёртка над LLMClient с логированием параметров.

Запуск:
    python bot.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.types import CallbackQuery, Message

from common.fsm import States
from common.logging_setup import setup_logging
from common.storage import MemoryStorage

from api_client import ApiClient, ApiError
from config import (
    ASK_MAX_TOKENS,
    ASK_QUERY,
    ASK_SYSTEM,
    ASK_TEMPERATURE,
    CLEAR_OK,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ERROR_API,
    ERROR_MAX_TOKENS,
    ERROR_NO_STATE,
    ERROR_TEMPERATURE,
    HELP_TEXT,
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
from tgbot import ConfigError, Router, TelegramBot, TelegramConfig, all_of
from tgbot.fsm import state_is, state_is_none
from tgbot.utils import safe_handler

logger = logging.getLogger(__name__)

#: Лимит одного сообщения в Telegram, символов
TG_MESSAGE_LIMIT: int = 4000


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _split_text(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    """Разбивает длинный текст на части по ``limit`` символов."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = text[:limit].rfind(" ")
        if cut < limit // 2:
            cut = limit
        part = text[:cut].strip()
        if part:
            parts.append(part)
        text = text[cut:].lstrip()
    return parts


def _parse_float(raw: str) -> float | None:
    """Разбирает число с точкой или запятой (0.7, 0,7)."""
    try:
        return float(raw.replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _parse_int(raw: str) -> int | None:
    """Разбирает целое число."""
    try:
        return int(float(raw.replace(",", ".").strip()))
    except (ValueError, TypeError):
        return None


def _format_usage(result: Any, api: ApiClient) -> str:
    """Формирует строку со статистикой токенов и стоимостью."""
    usage = getattr(result, "usage", None)
    if not usage:
        return ""
    cost = api.format_cost(api.estimate_cost(usage))
    return (
        f"\n\n📊 Токены: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}"
        f"\n💰 Стоимость: {cost}"
    )


async def _send_answer(
    bot: Any,
    chat_id: int,
    content: str,
    usage_line: str,
) -> None:
    """Отправляет ответ модели, разбивая длинный текст на части."""
    parts = _split_text(content)
    for index, part in enumerate(parts):
        text = part + usage_line if index == 0 else part
        await bot.send_message(chat_id, text, reply_markup=INLINE_KEYBOARD)


async def _ask_model(
    bot: Any,
    chat_id: int,
    ctx: ContextManager,
    api: ApiClient,
    user_id: int,
    text: str,
    temperature: float,
    max_tokens: int,
) -> None:
    """Отправляет реплику в модель и отвечает пользователю.

    Args:
        bot: Экземпляр ``aiogram.Bot``.
        chat_id: Идентификатор чата.
        ctx: Менеджер контекста.
        api: Клиент LLM API.
        user_id: Идентификатор пользователя.
        text: Текст реплики пользователя.
        temperature: Температура генерации.
        max_tokens: Лимит генерируемых токенов.
    """
    ctx.append_user(user_id, text)
    messages = ctx.messages(user_id)
    logger.info(
        "Отправка в модель: chat=%s messages=%d temp=%s max_tokens=%s "
        "roles=%s chars=%d",
        chat_id,
        len(messages),
        temperature,
        max_tokens,
        [m["role"] for m in messages],
        sum(len(m["content"]) for m in messages),
    )

    try:
        result = await asyncio.to_thread(
            api.ask,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (ApiError, LLMError) as exc:
        logger.error("Ошибка модели (chat=%s): %s", chat_id, exc)
        await bot.send_message(chat_id, f"{ERROR_API}\n\n{exc}")
        return

    ctx.append_assistant(user_id, result.content)
    await _send_answer(bot, chat_id, result.content, _format_usage(result, api))


# ---------------------------------------------------------------------------
# Построение роутера
# ---------------------------------------------------------------------------


def build_router(states: States, ctx: ContextManager, api: ApiClient) -> Router:
    """Создаёт роутер бота: FSM-сценарий, диалог, inline-кнопки.

    Args:
        states: Машина состояний (та же, что передана боту в ``states=``).
        ctx: Менеджер контекста диалога.
        api: Клиент LLM API.

    Returns:
        Роутер с обработчиками.
    """
    router = Router()

    # ===== Команды =====

    @router.command("start")
    @safe_handler
    async def cmd_start(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Сбрасывает историю и запускает пошаговую настройку."""
        states.reset(user_id)
        ctx.reset(user_id)
        states.set_state(user_id, S_QUERY)
        logger.info("Старт настройки: user=%s", user_id)
        await bot.send_message(message.chat.id, WELCOME_TEXT)

    @router.command("help")
    @safe_handler
    async def cmd_help(
        message: Message, bot: Any = None
    ) -> None:
        """Отправляет справку."""
        await bot.send_message(message.chat.id, HELP_TEXT)

    @router.command("reset")
    @safe_handler
    async def cmd_reset(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Очищает историю диалога и системное сообщение."""
        ctx.reset(user_id)
        states.reset(user_id)
        logger.info("Сброс по /reset: user=%s", user_id)
        await bot.send_message(message.chat.id, RESET_OK)

    # ===== Пошаговый ввод параметров =====

    @router.message(filt=state_is(states, S_QUERY))
    @safe_handler
    async def handle_query(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Принимает текст запроса и переходит к температуре."""
        text = (message.text or "").strip()
        if not text:
            return
        states.update_data(user_id, query=text)
        logger.info("Принят запрос: user=%s chars=%d", user_id, len(text))
        states.set_state(user_id, S_TEMPERATURE)
        await bot.send_message(message.chat.id, ASK_TEMPERATURE)

    @router.message(filt=state_is(states, S_TEMPERATURE))
    @safe_handler
    async def handle_temperature(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Принимает температуру и переходит к max_tokens."""
        temp = _parse_float((message.text or "").strip())
        if temp is None or not 0.0 <= temp <= 2.0:
            await bot.send_message(message.chat.id, ERROR_TEMPERATURE)
            return
        states.update_data(user_id, temperature=temp)
        logger.info("Принята температура: user=%s value=%s", user_id, temp)
        states.set_state(user_id, S_MAX_TOKENS)
        await bot.send_message(message.chat.id, ASK_MAX_TOKENS)

    @router.message(filt=state_is(states, S_MAX_TOKENS))
    @safe_handler
    async def handle_max_tokens(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Принимает max_tokens и переходит к системному сообщению."""
        max_tok = _parse_int((message.text or "").strip())
        if max_tok is None or not 1 <= max_tok <= 4000:
            await bot.send_message(message.chat.id, ERROR_MAX_TOKENS)
            return
        states.update_data(user_id, max_tokens=max_tok)
        logger.info("Принят max_tokens: user=%s value=%d", user_id, max_tok)
        states.set_state(user_id, S_SYSTEM)
        await bot.send_message(
            message.chat.id, ASK_SYSTEM, reply_markup=SKIP_SYSTEM_KEYBOARD
        )

    @router.message(filt=state_is(states, S_SYSTEM))
    @safe_handler
    async def handle_system(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Принимает системное сообщение и выполняет первый запрос."""
        sys_msg = (message.text or "").strip()
        states.update_data(user_id, system_message=sys_msg)
        logger.info(
            "Принято системное сообщение: user=%s chars=%d",
            user_id,
            len(sys_msg),
        )
        await _finish_setup(message.chat.id, bot, states, ctx, api, user_id)

    # ===== Inline-кнопки =====

    @router.callback(
        filt=all_of(
            lambda c: getattr(c, "data", None) == "setup:skip_system",
            state_is(states, S_SYSTEM),
        )
    )
    @safe_handler
    async def cb_skip_system(
        callback: CallbackQuery,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Пропускает системное сообщение и выполняет первый запрос."""
        states.update_data(user_id, system_message="")
        logger.info("Системное сообщение пропущено: user=%s", user_id)
        await callback.answer()
        await _finish_setup(
            callback.message.chat.id, bot, states, ctx, api, user_id
        )

    @router.callback(prefix="setup:again")
    @safe_handler
    async def cb_new_request(
        callback: CallbackQuery,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Перезапускает пошаговую настройку параметров."""
        states.reset(user_id)
        states.set_state(user_id, S_QUERY)
        logger.info("Новый запрос: user=%s", user_id)
        await callback.answer()
        await bot.send_message(callback.message.chat.id, ASK_QUERY)

    @router.callback(prefix="ctx:clear")
    @safe_handler
    async def cb_clear(
        callback: CallbackQuery,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Очищает историю диалога, оставляя параметры настройки."""
        ctx.clear(user_id)
        logger.info("Контекст очищен кнопкой: user=%s", user_id)
        await callback.answer("Контекст очищен")
        await bot.send_message(callback.message.chat.id, CLEAR_OK)

    # ===== Диалог =====

    @router.message(filt=state_is(states, S_CHAT))
    @safe_handler
    async def handle_chat(
        message: Message,
        bot: Any = None,
        states: Any = None,
        user_id: int | None = None,
    ) -> None:
        """Отвечает на сообщение пользователя в режиме диалога."""
        text = (message.text or "").strip()
        if not text:
            return
        data = states.get_data(user_id)
        await _ask_model(
            bot,
            message.chat.id,
            ctx,
            api,
            user_id,
            text,
            data.get("temperature", DEFAULT_TEMPERATURE),
            data.get("max_tokens", DEFAULT_MAX_TOKENS),
        )

    # ===== Фоллбэк: пользователь вне состояний =====

    @router.message(filt=state_is_none(states))
    @safe_handler
    async def handle_no_state(message: Message, bot: Any = None) -> None:
        """Подсказывает отправить /start, если состояние сброшено."""
        await bot.send_message(message.chat.id, ERROR_NO_STATE)

    return router


# ---------------------------------------------------------------------------
# Завершение настройки и первый запрос
# ---------------------------------------------------------------------------


async def _finish_setup(
    chat_id: int,
    bot: Any,
    states: Any,
    ctx: ContextManager,
    api: ApiClient,
    user_id: int,
) -> None:
    """Сохраняет настроенные параметры и выполняет первый запрос к модели.

    Args:
        chat_id: Идентификатор чата для ответа.
        bot: Экземпляр ``aiogram.Bot``.
        states: Машина состояний.
        ctx: Менеджер контекста.
        api: Клиент LLM API.
        user_id: Идентификатор пользователя.
    """
    data = states.get_data(user_id)
    query = data.get("query", "")
    temperature = data.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = data.get("max_tokens", DEFAULT_MAX_TOKENS)
    sys_msg = data.get("system_message", "")

    if not query:
        states.reset(user_id)
        await bot.send_message(chat_id, ERROR_NO_STATE)
        return

    # Системное сообщение хранится отдельно от истории и не обрезается
    ctx.set_system_message(user_id, sys_msg)
    # Переходим в режим диалога до запроса: ошибка API не должна «закрывать» бота
    states.set_state(user_id, S_CHAT)
    logger.info(
        "Настройка завершена: user=%s temp=%s max_tokens=%s system=%s",
        user_id,
        temperature,
        max_tokens,
        bool(sys_msg),
    )
    await bot.send_message(
        chat_id,
        f"✅ Параметры приняты:\n"
        f"• модель: {MODEL}\n"
        f"• температура: {temperature}\n"
        f"• max_tokens: {max_tokens}\n"
        f"• system_message: {sys_msg if sys_msg else '(не задан)'}\n\n"
        f"Отвечаю на первый запрос…",
    )
    await _ask_model(bot, chat_id, ctx, api, user_id, query, temperature, max_tokens)


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------


def main() -> int:
    """Настраивает логирование, создаёт компоненты и запускает бота.

    Returns:
        Код возврата: 0 — успех, 1 — ошибка конфигурации.
    """
    setup_logging()

    try:
        config = TelegramConfig.from_env()
    except ConfigError as exc:
        logger.error("Ошибка конфигурации бота: %s", exc)
        return 1

    try:
        api_client = ApiClient(
            model=MODEL,
            default_temperature=DEFAULT_TEMPERATURE,
            default_max_tokens=DEFAULT_MAX_TOKENS,
        )
    except LLMError as exc:
        logger.error("Ошибка конфигурации нейросети: %s", exc)
        return 1

    # Хранение контекста — в памяти процесса (MemoryStorage)
    fsm_states = States(MemoryStorage())
    ctx_manager = ContextManager(
        max_messages=MAX_CONTEXT_MESSAGES,
        max_chars=MAX_CONTEXT_CHARS,
    )

    bot = TelegramBot(
        config=config,
        router=build_router(fsm_states, ctx_manager, api_client),
        states=fsm_states,
        context=ctx_manager,
        service_handlers=False,
    )

    logger.info(
        "Бот запускается: модель=%s temp=%s max_tokens=%s context=%d реплик",
        MODEL,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_TOKENS,
        MAX_CONTEXT_MESSAGES,
    )
    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
