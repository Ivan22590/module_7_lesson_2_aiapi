"""Инфраструктура Telegram-бота (aiogram): инициализация, регистрация, polling.

Модуль не содержит бизнес-логики: внешний проект передаёт свои обработчики
через :class:`~tgbot.router.Router`, а бот асинхронно доставляет им апдейты
и аккуратно логирует обмен.

Пример:
    >>> from tgbot import TelegramBot, Router
    >>> router = Router()
    >>> @router.command("hello")
    ... async def hello(message, bot=None):
    ...     await bot.send_message(message.chat.id, "Hello!")
    >>> bot = TelegramBot(router=router)
    >>> bot.run()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .config import ConfigError, TelegramConfig
from .handlers import build_service_router
from .middlewares import install_logging
from .router import Router

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

    from common.context import ChatContextStore
    from common.fsm import States
    from common.keyboards import Keyboard

logger = logging.getLogger(__name__)


class TelegramBot:
    """Готовый к запуску Telegram-бот (aiogram) с внешними обработчиками.

    Args:
        config: Конфигурация бота. ``None`` — создать из окружения
            (обязательна только переменная ``TG_BOT_API_KEY``).
        router: Роутер с обработчиками внешнего проекта. ``None`` — пустой
            роутер (тогда работать будут только служебные обработчики).
        service_handlers: Подключать ли служебные ``/start``, ``/help`` и
            echo. Они регистрируются после внешних, поэтому не перехватывают
            команды проекта.
        with_logging: Подключать ли сквозное логирование входящих и
            исходящих сообщений.
        states: Машина состояний ``common.fsm.States``. Если задана,
            подключается middleware, инъецирующий в обработчики ``states``,
            ``context`` (при переданном) и ``user_id``. ``None`` — состояния
            не подключаются (поведение бота не меняется).
        context: Хранилище истории диалога ``common.context.ChatContextStore``
            (имеет смысл вместе с ``states``; попадает в kwarg ``context``).

    Raises:
        ConfigError: если не задан токен бота.
    """

    def __init__(
        self,
        config: TelegramConfig | None = None,
        router: Router | None = None,
        *,
        service_handlers: bool = True,
        with_logging: bool = True,
        states: "States | None" = None,
        context: "ChatContextStore | None" = None,
    ) -> None:
        self.config: TelegramConfig = (
            config if config is not None else TelegramConfig.from_env()
        )
        self.router: Router = router if router is not None else Router()
        self.states = states
        self.context = context
        self._service_handlers = service_handlers
        self._with_logging = with_logging
        self._polling_task: asyncio.Task[Any] | None = None

        # Импорт aiogram здесь, чтобы ошибка конфигурации возникала раньше
        # ошибки импорта — так проще диагностировать незаполненный .env
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties

        self.bot: Bot = Bot(
            self.config.token,
            default=DefaultBotProperties(parse_mode=self.config.parse_mode or None),
        )
        self.dispatcher: Dispatcher = Dispatcher()
        if self._with_logging:
            install_logging(self.dispatcher, self.bot)
        if states is not None:
            # Ленивый импорт: модуль работает и без пакета common
            from .fsm import make_states_middleware

            self.dispatcher.update.outer_middleware(
                make_states_middleware(states, context)
            )
            logger.debug("Хранение состояний подключено (context=%s)", context is not None)
        logger.info(
            "Telegram-бот инициализирован (parse_mode=%s)", self.config.parse_mode
        )

    # ------------------------------------------------------------------
    # Регистрация обработчиков
    # ------------------------------------------------------------------

    def register(self, *initializers: Any) -> "TelegramBot":
        """Дополнительно регистрирует обработчики в роутере бота.

        Args:
            *initializers: Функции ``fn(router)`` или объекты с методом
                ``register(router)``.

        Returns:
            Тот же объект бота (для цепочки вызовов).
        """
        self.router.include(*initializers)
        return self

    def _apply_handlers(self) -> None:
        """Применяет роутеры к диспетчеру: сначала внешние, затем служебные."""
        self.router.register(self.dispatcher, self.bot)
        if self._service_handlers:
            build_service_router().register(self.dispatcher, self.bot)
        logger.debug("Обработчики бота применены")

    # ------------------------------------------------------------------
    # Отправка сообщений с клавиатурами (пример интеграции)
    # ------------------------------------------------------------------

    async def send_keyboard(self, chat_id: int, text: str, keyboard: Keyboard) -> None:
        """Отправляет сообщение с универсальной клавиатурой (пример интеграции).

        Клавиатура описывается в абстрактном формате ``common.keyboards`` —
        тот же объект отправляется в VK-бот через
        :meth:`vkbot.bot.VKBot.send_keyboard`. Метод содержит только
        инфраструктурный код и конвертацию, никакой бизнес-логики.

        Импорт адаптера ленивый: модуль ``tgbot`` работает и без пакета
        ``common``, пока метод не вызван.

        Args:
            chat_id: Идентификатор чата Telegram.
            text: Текст сообщения.
            keyboard: Универсальная клавиатура ``common.keyboards.Keyboard``.

        Raises:
            ValueError: если клавиатура не содержит кнопок.
        """
        from common.keyboards import TelegramKeyboardAdapter

        reply_markup = TelegramKeyboardAdapter().convert(keyboard)
        await self.bot.send_message(chat_id, text, reply_markup=reply_markup)
        logger.debug(
            "Сообщение с клавиатурой отправлено chat=%s inline=%s кнопок=%d",
            chat_id,
            keyboard.inline,
            len(keyboard),
        )

    # ------------------------------------------------------------------
    # Запуск
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Запускает long-polling асинхронно (блокирует до остановки).

        Метод публичен: его можно ждать внутри собственного event loop
        (``await bot.start()``); синхронная обёртка — :meth:`run`.

        ``allowed_updates`` передаётся явно и неизменно: Telegram запоминает
        последнюю заданную настройку, поэтому при ``None`` сервер продолжает
        применять старую — и inline-кнопки могут молча перестать доходить.
        """
        self._apply_handlers()
        logger.info(
            "Бот запущен, начинаем polling (timeout=%ss)...",
            self.config.polling_timeout,
        )
        self._polling_task = asyncio.current_task()
        try:
            await self.dispatcher.start_polling(
                self.bot,
                polling_timeout=self.config.polling_timeout,
                allowed_updates=list(self.config.allowed_updates),
            )
        except asyncio.CancelledError:
            logger.info("Polling остановлен (отмена задачи)")
            raise
        finally:
            self._polling_task = None

    def run(self) -> None:
        """Запускает бота: выполняет :meth:`start` в новом event loop (блокирует).

        Ctrl+C останавливает polling корректно; ошибки конфигурации
        и непредвиденные исключения логируются и пробрасываются дальше.
        """
        try:
            asyncio.run(self.start())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Остановка по сигналу пользователя")
        except asyncio.CancelledError:
            logger.info("Polling остановлен методом stop()")
        except Exception:
            logger.exception("Работа бота прервана непредвиденной ошибкой")
            raise

    def stop(self) -> None:
        """Останавливает polling (безопасно вызывать из другого потока).

        Вступает в силу после текущего long-poll-запроса: отменяет задачу,
        выполняющую polling. Если polling не запущен, метод безопасно
        ничего не делает.
        """
        task = self._polling_task
        if task is None:
            logger.debug("Polling не запущен — stop() нечего останавливать")
            return
        loop = task.get_loop()

        def _cancel() -> None:
            if not task.done():
                task.cancel()

        try:
            loop.call_soon_threadsafe(_cancel)
        except RuntimeError:  # loop уже закрыт — останавливать нечего
            logger.debug("Event loop уже остановлен — stop() пропущен")


__all__ = ("TelegramBot", "ConfigError")
