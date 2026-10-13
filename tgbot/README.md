# /tgbot — универсальная инфраструктура Telegram-бота

Модуль инкапсулирует всё, что нужно для Telegram-бота на
[aiogram 3](https://docs.aiogram.dev/): инициализацию, конфигурацию,
роутер внешних обработчиков, сквозное логирование и long-polling.
**Бизнес-логики внутри нет** — модуль готов к использованию
в любом другом проекте.

Бот полностью асинхронный: обработчики объявляются как `async def`,
а запуск — привычный синхронный `TelegramBot.run()` (внутри —
`asyncio.run`). Публичный API модуля (имена в `tgbot.__all__`) не
изменялся — изменились только реализация и контракт обработчиков.

## Возможности

- асинхронный event loop aiogram: обработчики не блокируют друг друга;
- роутер для регистрации внешних обработчиков: команды, сообщения, callback-кнопки;
- фильтры (`commands`, `regexp`, `callback_prefix`, `any_text`);
- сквозное логирование входящих апдейтов и **всех** исходящих вызовов API
  (middleware диспетчера и сессии бота);
- хранение состояний: опциональные `states=` / `context=` поверх `/common`
  (инъекция в обработчики + фильтры `state_is` / `state_is_none`);
- служебные заглушки `/start`, `/help`, echo — регистрируются последними;
- явный фиксированный `allowed_updates` (иначе inline-кнопки перестают доходить);
- **обязательна только одна переменная** — `TG_BOT_API_KEY`.

## Структура

```
tgbot/
├── __init__.py      # публичный интерфейс
├── bot.py           # TelegramBot: инициализация, регистрация, start()/run()/stop()
├── config.py        # TelegramConfig.from_env(), ConfigError
├── router.py        # Router — реестр внешних обработчиков (над aiogram.Router)
├── handlers.py      # служебные /start, /help, echo (заглушки)
├── middlewares.py   # сквозное логирование вход/исход
├── filters.py       # предикаты для сопоставления апдейтов
├── fsm.py           # адаптер хранения состояний (middleware + фильтры)
├── types.py         # служебные типы (Handler, RouterInitializer)
├── utils.py         # safe_handler (async), preview
└── README.md
```

## Конфигурация

| Переменная | Обязательна | По умолчанию | Описание |
|---|---|---|---|
| `TG_BOT_API_KEY` | **да** | — | токен бота от [@BotFather](https://t.me/BotFather) |
| `TG_BOT_PARSE_MODE` | нет | `HTML` | режим разметки сообщений |
| `TG_POLLING_TIMEOUT` | нет | `30` | таймаут long-polling, сек |

## Запуск

Из корня проекта (зависимости уже установлены в `.venv`):

```bash
.venv\Scripts\python.exe run_tgbot.py
```

## Использование в другом проекте

Скопируйте папку `tgbot/` и положите рядом `.env` с `TG_BOT_API_KEY=...`:

```python
from tgbot import TelegramBot, Router

router = Router()

@router.command("hello")
async def hello(message, bot=None):
    await bot.send_message(message.chat.id, "Hello!")

@router.callback(prefix="menu:")
async def on_menu(call, bot=None):
    await bot.answer_callback_query(call.id, "Открыто меню")

@router.message()                  # любое текстовое сообщение
async def on_text(message, bot=None):
    await bot.send_message(message.chat.id, message.text)

TelegramBot(router=router).run()
```

Обработчики должны быть **`async`** — объект `bot` это `aiogram.Bot`,
и все его методы асинхронные. Регистрация синхронного обработчика
(`def`) не запрещена, но сопровождается предупреждением в лог: такой
обработчик не сможет отправлять сообщения.

Внешние обработчики регистрируются **до** служебных, поэтому команда
вашего проекта всегда важнее заглушки.

### Запуск внутри своего event loop

`TelegramBot.run()` создаёт новый event loop (`asyncio.run`) и блокирует
выполнение — как в прежней синхронной версии. Если event loop уже
работает (например, в веб-приложении), используйте асинхронный метод:

```python
bot = TelegramBot(router=router)
await bot.start()        # ждёт до остановки polling
bot.stop()               # корректная остановка (можно из другого потока)
```

### Подключение к нейросети

`/tgbot` намеренно не знает про `/llm`. Связывание — в вашем коде.
Клиент `/llm` синхронный, поэтому вызов оборачивается в
`asyncio.to_thread`, чтобы нейросеть не блокировала event loop бота:

```python
import asyncio

from llm import LLMClient
from tgbot import TelegramBot, Router

client = LLMClient()
router = Router()

@router.message()
async def ask_llm(message, bot=None):
    result = await asyncio.to_thread(
        client.chat, [{"role": "user", "content": message.text}]
    )
    await bot.send_message(message.chat.id, result.content)

TelegramBot(router=router).run()
```

### Хранение состояний (FSM и история диалога)

Память о диалоге (состояние многошагового сценария + история реплик
с нейросетью) живёт в `/common` — см.
[common/storage/README.md](../common/storage/README.md). Модуль `/tgbot`
подключает её **опциональными** параметрами; без них поведение бота
не меняется:

```python
from common.context import ChatContextStore
from common.fsm import States
from common.storage import JsonFileStorage
from tgbot import TelegramBot, Router, state_is, state_is_none

storage = JsonFileStorage("state/bot_state.json")   # переживает перезапуск
states = States(storage)                            # состояние + данные шага
context = ChatContextStore(storage, max_messages=20)  # история для LLM

router = Router()

@router.command("settings")
async def settings(message, bot=None, states=None, user_id=None):
    states.set_state(user_id, "Settings:waiting_input")
    await bot.send_message(message.chat.id, "Пришли новый системный промпт:")

@router.message(filt=state_is(states, "Settings:waiting_input"))
async def collect_prompt(message, bot=None, states=None, context=None, user_id=None):
    context.append(user_id, "system", message.text)
    states.reset(user_id)
    await bot.send_message(message.chat.id, "Сохранено!")

@router.message(filt=state_is_none(states))   # только вне сценария
async def chat(message, bot=None, context=None, user_id=None):
    context.append(user_id, "user", message.text)
    result = await asyncio.to_thread(client.chat, context.history(user_id))
    context.append(user_id, "assistant", result.content)
    await bot.send_message(message.chat.id, result.content)

TelegramBot(router=router, states=states, context=context).run()
```

Что происходит под капотом:

- `TelegramBot(states=..., context=...)` ставит outer-middleware диспетчера,
  которое кладёт в контекст обработчика `states`, `context` и `user_id` —
  обработчику достаточно объявить эти параметры (с дефолтами `None`);
- фильтры `state_is(states, "Имя")` / `state_is_none(states)` читают
  текущее состояние пользователя и работают как `filt=` при регистрации;
- имена состояний — произвольные строки: FSM `/common` одинаково работает
  в Telegram- и VK-боте.

Полный рабочий пример соединения с нейросетью — `run_chat_llm.py`
в корне проекта.

## Логирование

Модуль использует логгер `tgbot.*`. Настройка уровня и файла — общей функцией
`logging_setup.setup_logging()` из `common/logging_setup.py` (`LOG_LEVEL`, по умолчанию
`INFO`; по умолчанию логи пишутся в консоль **и** в `logs/app.log`). В лог
попадают: входящий апдейт (пользователь, чат, текст), исходящий ответ
(адресат, текст — ловится middleware сессии, поэтому видны и отправки,
и редактирование, и ответы на кнопки) и ошибки. Токен бота в логи не пишется.

## Миграция с pyTelegramBotAPI (telebot)

Модуль переехал с telebot на aiogram. Публичные имена (`tgbot.__all__`)
сохранились, но контракт изменился:

| Было (telebot) | Стало (aiogram) |
|---|---|
| `def handler(message, bot=None)` | `async def handler(message, bot=None)` — **обязательно** |
| `bot.send_message(...)` без `await` | `await bot.send_message(...)` |
| `TelegramBot.send_keyboard(...)` (sync) | `await TelegramBot.send_keyboard(...)` |
| `TelegramBot.run()` — единственный способ запуска | `run()` (синхронный) + `start()`/`stop()` (async) |
| `install_logging(bot)` | `install_logging(dispatcher, bot)` |
| `describe_outgoing(name, args, kwargs)` | `describe_outgoing(method)` — объект метода aiogram |
| объекты `telebot.types.*` в обработчиках | объекты `aiogram.types.*` (`Message`, `CallbackQuery`) |

Фильтры (`commands`, `regexp`, `callback_prefix`, `any_text`) продолжают
работать с объектами aiogram как прежде. Синхронные обработчики по-прежнему
регистрируются, но получают предупреждение в лог и не умеют отправлять
сообщения — преобразуйте их в `async def`.
