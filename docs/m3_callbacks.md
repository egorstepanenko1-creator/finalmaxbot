# M3: карта callback payload (MAX inline_keyboard)

Все новые кнопки используют префикс версии `v1` и разделитель `|`. При смене контракта вводится `v2|...`.

## Режим

| Payload | Действие |
|---------|----------|
| `v1\|mode\|consumer` | Режим «для себя» + главное меню consumer |
| `v1\|mode\|business` | Режим «для бизнеса» + главное меню business |
| `mode:consumer` | Legacy, эквивалент consumer |
| `mode:business` | Legacy, эквивалент business |

## Consumer (главное меню)

| Payload | Действие |
|---------|----------|
| `v1\|consumer\|ask_question` | Flow `consumer.ask_question` → ждём текст вопроса |
| `v1\|consumer\|create_image` | Flow `consumer.create_image` → ждём описание картинки |
| `v1\|consumer\|make_greeting` | Flow `consumer.make_greeting` → ждём повод/адресата |
| `v1\|consumer\|my_stars` | Показать баланс звёзд (ledger) |
| `v1\|consumer\|invite_friend` | Заглушка приглашения (billing stub) |
| `v1\|consumer\|subscription` | Заглушка подписки (Т-Банк позже) |

## Business (главное меню)

| Payload | Действие |
|---------|----------|
| `v1\|business\|create_vk_post` | Flow `business.create_vk_post` → ждём тему поста |
| `v1\|business\|create_image` | Flow `business.create_image` → ждём описание |
| `v1\|business\|my_stars` | Звёзды |
| `v1\|business\|invite_friend` | Приглашение (stub) |
| `v1\|business\|subscription` | Подписка (stub) |

Константы: `packages/shared/callbacks.py`.
