# /common — хранение состояний (storage + FSM + контекст LLM)

Универсальная подсистема памяти ботов. Стоит **над** любым бэкендом
хранилища и **под** адаптерами обоих ботов, поэтому модуль не зависит ни
от aiogram, ни от vkbottle, ни от `/llm`.

```
┌─────────────────────────── обработчики ботов ───────────────────────────┐
│  tgbot (middleware+фильтры)              vkbot (CommonStateDispenser)   │
└──────────────┬──────────────────────────────────┬───────────────────────┘
               │                                  │
     common.fsm.States                 common.context.ChatContextStore
     (состояние + данные шага)         (история диалога с нейросетью)
               └──────────────┬───────────────────┘
                   common.storage.Storage (ABC)
                   ├── MemoryStorage    — в памяти процесса
                   └── JsonFileStorage  — JSON-файл, атомарная запись
```

## Хранилище: `common.storage`

Единый контракт для всех бэкендов (ключ → значение):

* ключ — непустая строка;
* значение — JSON-совместимый тип (`None`, `bool`, `int`, `float`, `str`,
  `list`, `dict`) — бэкенд переключается без изменения потребителей;
* TTL (время жизни) — необязательный, в секундах, чистится лениво;
* `keys(prefix)` / `clear(prefix)` — работа по префиксу ключей.

```python
from common.storage import JsonFileStorage, MemoryStorage, StorageError

storage = JsonFileStorage("state/bot_state.json")   # или MemoryStorage()
storage.set("user:1", {"state": "menu"}, ttl=3600)
storage.get("user:1")        # {'state': 'menu'} (копия)
storage.keys("user:")        # ['user:1']
```

Готовые бэкенды:

| Бэкенд | Персистентность | Особенности |
|---|---|---|
| `MemoryStorage` | нет (память процесса) | тесты, демо, быстрый старт |
| `JsonFileStorage` | JSON-файл | атомарная запись (tmp + `os.replace`), ленивая загрузка, потокобезопасен |

Ограничения `JsonFileStorage`: рассчитан на **один процесс** (типичный бот
на polling). Для нескольких процессов добавьте свой бэкенд по
интерфейсу `Storage` (например, Redis/PostgreSQL). Повреждённый JSON-файл
даёт `StorageError` — данные не затираются молча.

## Машина состояний: `common.fsm.States`

Хранит на пользователя пару «имя состояния (строка) + данные шага
(словарь)». Имя состояния — произвольная строка: каждый бот мапит на неё
свои нативные состояния.

```python
from common.fsm import States
from common.storage import JsonFileStorage

states = States(JsonFileStorage("state/bot_state.json"))
states.set_state(42, "Settings:waiting_input", ttl=600)
states.get_state(42)                    # 'Settings:waiting_input'
states.update_data(42, attempts=1)      # {'attempts': 1}
states.set_state(42, None)              # снять состояние (данные остаются)
states.reset(42)                        # очистить состояние и данные
```

## История диалога с нейросетью: `common.context.ChatContextStore`

Последние реплики «пользователь ↔ нейросеть» в формате, который напрямую
принимает `llm.LLMClient.chat` — список словарей `{"role", "content"}`.
История ограничивается по числу реплик и по суммарному бюджету символов
(старые реплики отбрасываются — запрос к модели не растёт бесконечно).

```python
from common.context import ChatContextStore

context = ChatContextStore(storage, max_messages=20)
context.append(42, "user", "Привет!")
context.append(42, "assistant", "Здравствуйте!")
client.chat(context.history(42))        # готовый список реплик
context.clear(42)
```

## Подключение к ботам

Адаптеры лежат в самих ботах и подключаются опциональными параметрами —
без них поведение ботов не меняется.

Telegram (`tgbot`):

```python
from tgbot import Router, TelegramBot, state_is

router = Router()

@router.message(filt=state_is(states, "Settings:waiting_input"))
async def collect(message, bot=None, states=None, context=None, user_id=None):
    context.append(user_id, "system", message.text)
    states.reset(user_id)

bot = TelegramBot(router=router, states=states, context=context)
```

Middleware инъецирует в обработчик `states`, `context` и `user_id`
(объявляйте их параметрами с дефолтами `None`). Для «обычного» обработчика
есть фильтр `state_is_none(states)`.

VK (`vkbot`):

```python
from vkbot import VKBot
from vkbottle import BaseStateGroup

class Menu(BaseStateGroup):
    OPEN = "open"

vkbot = VKBot(states=states)            # диспенсер поверх common.fsm.States

@vkbot.on_message(state=Menu.OPEN)      # нативные правила vkbottle работают
async def in_menu(message): ...
```

Полный демо-сценарий (чат с нейросетью + FSM `/settings` + JSON-файл
состояний): `run_chat_llm.py` в корне проекта.

## Ограничения

* значения — только JSON-совместимые типы (общий контракт бэкендов);
* **секреты в состояние не кладутся**: файл состояний хранится в
  `state/` (в `.gitignore`), но токены/ключи держите только в окружении;
* TTL чистится лениво (при обращении) — истёкшая запись исчезает при
  первом `get`/`keys`;
* `JsonFileStorage` — для одного процесса (polling-бота).

## Тесты

```powershell
.venv\Scripts\python.exe -m unittest tests.test_storage tests.test_fsm tests.test_context -v
```
