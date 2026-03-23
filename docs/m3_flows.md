# M3: карта state machine

Состояния хранятся в `conversations.flow_state` (`packages/shared/states.py`).

## Общее

- Пока `users.current_mode` пуст — показывается только выбор режима (кнопки).
- В `idle` свободный текст подсказывает пользоваться меню (кнопки прилагаются).
- После успешного текстового сценария снова показывается главное меню режима.

## Consumer

| Состояние | Вход | Следующий ввод пользователя | Результат |
|-----------|------|----------------------------|-----------|
| `idle` | Меню / завершение flow | Текст без кнопки | Подсказка + меню |
| `consumer.await_question` | «Задать вопрос» | Текст | Ответ через `TextGenerationPort`, `usage_events.kind=text_question` |
| `consumer.await_greeting_prompt` | «Поздравление» | Текст | Текст поздравления, `usage_events.kind=text_greeting` |
| `consumer.await_image_prompt` | «Сделать картинку» | Текст | `generation_jobs` placeholder + детерминированный ack, `usage_events.kind=image_intake` |

## Business

| Состояние | Вход | Следующий ввод | Результат |
|-----------|------|----------------|-----------|
| `idle` | — | — | — |
| `business.await_vk_post_prompt` | «Пост для VK» | Текст | Черновик поста, `usage_events.kind=text_vk_post` |
| `business.await_image_prompt` | «Сделать картинку» | Текст | `generation_jobs` + ack |

## Сервисы

- `apps/bot/interaction_router.py` — маршрутизация по `update_type`.
- `apps/bot/state_machine_service.py` — логика состояний и меню.
- `apps/bot/max_client.py` — транспорт MAX.
- `packages/providers/text_generation.py` — AI (Yandex или stub).
- `packages/billing/stub.py` — оплата/подписка (заглушка).
