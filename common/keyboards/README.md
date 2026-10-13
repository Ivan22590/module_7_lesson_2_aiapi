# `/common/keyboards` — универсальные кнопочные клавиатуры

Система описания кнопочных клавиатур, одинаковая для Telegram- и VK-бота.
Одно и то же описание конвертируется адаптерами в нативные форматы обоих
мессенджеров, поэтому интерфейсы выглядят одинаково. Пакет не содержит
прикладной бизнес-логики и не зависит от `/tgbot`, `/vkbot` и `/llm` —
им можно пользоваться в любом другом проекте.

## Архитектура

```
common/
└── keyboards/
    ├── models.py             # абстрактные модели: Button, Keyboard, ButtonType, ButtonColor
    ├── builder.py            # KeyboardBuilder — создание клавиатур цепочкой вызовов
    ├── telegram_adapter.py   # TelegramKeyboardAdapter → объекты aiogram
    ├── vk_adapter.py         # VKKeyboardAdapter → JSON-строка VK API
    ├── __init__.py           # публичный интерфейс
    └── README.md             # эта документация
```

Направление зависимостей однонаправленное: адаптеры знают о мессенджерах,
но мессенджеры не знают о клавиатурах — `/tgbot` и `/vkbot` подключают
адаптеры лениво, только внутри методов отправки.

```
Keyboard (абстракция) ──► TelegramKeyboardAdapter ──► ReplyKeyboardMarkup / InlineKeyboardMarkup
        │
        └──────────────► VKKeyboardAdapter ────────► JSON-строка для параметра keyboard
```

## Модели

- `Button` — одна кнопка: `text`, `type`, `payload` (словарь данных),
  `row`/`column` (раскладка), `color` (для VK), `url`, `callback_data`.
- `Keyboard` — клавиатура: список кнопок + параметры `one_time`, `resize`,
  `inline`. Раскладка вычисляется методом `get_rows()`; есть
  `buttons_at(row)` и `buttons_in_column(column)` для доступа
  по строкам и колонкам.
- `ButtonType` — типы кнопок: `TEXT`, `URL`, `CALLBACK`, `LOCATION`,
  `PHONE`, `PAY`.
- `ButtonColor` — цвета: `DEFAULT`, `PRIMARY`, `SECONDARY`, `POSITIVE`,
  `NEGATIVE` (используются в VK).

Все параметры валидируются: пустой текст, отрицательные строка/колонка,
`URL` без адреса, `CALLBACK` без данных вызывают `ValueError`.

## Правила раскладки

- кнопки с явными `row`/`column` встают по указанным позициям;
- кнопка без `row` получает отдельную новую строку ниже всех явно
  заданных (в порядке добавления);
- кнопки без `column` идут после кнопок с явной колонкой;
- пропущенные номера строк становятся пустыми (адаптеры их пропускают);
- пропуски в колонках не сохраняются — внутри строки кнопки идут подряд.

## Builder: создание клавиатур

```python
from common.keyboards import KeyboardBuilder, ButtonColor

# Обычная (reply) клавиатура — методы вызываются цепочкой
keyboard = (KeyboardBuilder()
    .add_text_button("Меню", row=0, column=0)
    .add_text_button("Настройки", row=0, column=1)
    .add_url_button("Сайт", "https://example.com", row=1, column=0)
    .add_callback_button("Действие", "action_1", row=2, column=0)
    .build())

# Кнопки без явной строки встают каждая в свою новую строку
keyboard = (KeyboardBuilder()
    .add_text_button("Да", color=ButtonColor.POSITIVE)
    .add_text_button("Нет", color=ButtonColor.NEGATIVE)
    .build())

# Inline-клавиатура (под сообщением)
inline = (KeyboardBuilder(inline=True)
    .add_callback_button("Открыть", "menu:open")
    .add_callback_button("Закрыть", "menu:close")
    .build())

# Геолокация, телефон и оплата
special = (KeyboardBuilder()
    .add_location_button("Отправить геопозицию")
    .add_phone_button("Отправить номер")
    .add_pay_button("Оплатить", payload={"hash": "action=pay&item=1"})
    .build())
```

Методы builder'а: `add_text_button`, `add_url_button`, `add_callback_button`,
`add_location_button`, `add_phone_button`, `add_pay_button`, `add_button`
(готовая модель `Button`). Каждый возвращает `self`, поэтому вызовы
сцепляются; `build()` возвращает независимую копию клавиатуры.

## Адаптеры

### Telegram

```python
from common.keyboards import TelegramKeyboardAdapter

reply_markup = TelegramKeyboardAdapter().convert(keyboard)
await bot.send_message(chat_id, "Выберите действие:", reply_markup=reply_markup)
```

- результат — объекты aiogram `ReplyKeyboardMarkup` (учитываются `resize`,
  `one_time`) или `InlineKeyboardMarkup`;
- `inline=True` → `InlineKeyboardMarkup`;
- `LOCATION`/`PHONE` → кнопки с `request_location`/`request_contact`;
- `CALLBACK` → `callback_data`, `URL` → `url`;
- `TEXT` в inline → callback-кнопка с текстом в качестве данных;
- `callback_data` длиннее 64 байт усекается с предупреждением в лог.

### VK

```python
from common.keyboards import VKKeyboardAdapter

keyboard_json = VKKeyboardAdapter().convert(keyboard)
await bot.api.messages.send(peer_id=peer_id, message="Выберите действие:",
                            keyboard=keyboard_json, random_id=0)
```

- результат — JSON-строка `{"one_time", "inline", "buttons": [[...]]}`
  для параметра `keyboard` VK API;
- `TEXT` → `text` с цветом, `URL` → `open_link`, `CALLBACK` → `callback`,
  `LOCATION` → `location`, `PAY` → `vkpay` (нужен `payload["hash"]`);
- `callback_data` переносится в payload кнопки VK под ключом
  `callback_data`, чтобы обработчики обоих ботов видели одни данные;
- цвета маппятся: `ButtonColor.PRIMARY` → `primary` и т.д.;
- `resize` VK API не поддерживает — свойство игнорируется.

## Поддерживаемые типы кнопок

| Тип | Назначение | Telegram (reply) | Telegram (inline) | VK |
|---|---|---|---|---|
| `TEXT` | обычная текстовая | ✅ | ✅ (callback с текстом) | ✅ `text` |
| `URL` | ссылка | ⚠️ обычная (текст) | ✅ `url` | ✅ `open_link` |
| `CALLBACK` | данные обработчику | ⚠️ обычная (текст) | ✅ `callback_data` | ✅ `callback` |
| `LOCATION` | запрос геолокации | ✅ `request_location` | ⚠️ callback (fallback) | ✅ `location` |
| `PHONE` | запрос телефона | ✅ `request_contact` | ⚠️ callback (fallback) | ⚠️ текст (fallback) |
| `PAY` | оплата | ⚠️ обычная (текст) | ⚠️ callback (fallback) | ✅ `vkpay` (нужен `hash`) |

⚠️ — платформа не поддерживает тип в этом контексте: адаптер заменяет
кнопку на совместимую и пишет `logger.warning`.

Лимиты платформ: Telegram — `callback_data` до 64 байт; VK — до 5 кнопок
в строке, до 10 строк (обычная) и 6 строк (inline). Превышения лимитов VK
логируются предупреждением.

## Использование в ботах

`/tgbot` и `/vkbot` содержат готовые методы-примеры, принимающие одну и ту
же абстрактную клавиатуру:

```python
from common.keyboards import KeyboardBuilder

keyboard = (KeyboardBuilder()
    .add_text_button("Кнопка 1", row=0, column=0)
    .add_text_button("Кнопка 2", row=0, column=1)
    .build())

# Telegram (асинхронный метод — бот на aiogram)
await tg_bot.send_keyboard(chat_id, "Выберите действие:", keyboard)

# VK (асинхронный метод)
await vk_bot.send_keyboard(peer_id, "Выберите действие:", keyboard)
```

## Расширение: добавление нового типа кнопки

1. Добавьте значение в `ButtonType` (или `ButtonColor`) в `models.py`.
2. При необходимости — новые поля и проверки в `Button.__post_init__`.
3. Опишите поведение в `telegram_adapter.py`:
   `_reply_button` (для обычной клавиатуры) и `_inline_button` (для inline).
4. Опишите поведение в `vk_adapter.py`: новая ветка в `_action_dict`
   (учтите, что цвет поддерживается VK только у `text`/`callback`).
5. Добавьте метод `add_*_button` в `builder.py` (возвращает `self`).
6. Обновите таблицу типов в этом README.
7. Добавьте тесты в `tests/test_keyboards.py` (конвертация в оба формата
   и ожидаемые предупреждения).

Новые типы не должны ссылаться на `/tgbot` и `/vkbot` — вся
платформенная специфика остаётся внутри адаптеров.

## Тесты

```bash
# из корня проекта, без сети и реальных API-вызовов
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Покрытие: цепочка вызовов builder'а, раскладка по строкам/колонкам,
конвертация в Telegram (флаги, запрос локации/контакта, inline-кнопки,
усечение `callback_data`) и в VK (JSON-структура, цвета, payload,
fallback-кнопки, лимиты), а также сохранение раскладки в обоих форматах.
