# M4: монетизация, квоты, entitlements, paywall

## Коды планов

| Код | Описание |
|-----|----------|
| `consumer_free` | Бесплатный потребитель (по умолчанию без активной подписки) |
| `consumer_plus_290` | Платный потребитель (активная подписка с этим `plan_code`) |
| `business_free` | Бизнес без платной подписки (`current_mode=business`) |
| `business_marketer_490` | Бизнес-маркетолог (активная подписка) |

Лимиты и флаги задаются в `packages/entitlements/plan_definitions.py` и числами в `Settings` (префикс `m4_` в `packages/shared/settings.py`).

## Квоты (кратко)

- **Consumer free — «картиночные» слоты:** `text_greeting` и `consumer_image_intake` (и legacy `image_intake` без `mode=business`) суммируются в **скользящие 24 часа**. Лимит: `m4_consumer_free_images_per_rolling_24h` (по умолчанию 3).
- **Consumer plus / business marketer — картинки:** календарный месяц, `m4_consumer_plus_max_images_per_month` / `m4_business_marketer_max_images_per_month`.
- **Текстовые вопросы (`text_question`):** отдельный fair-use rolling 24h на план (`m4_*_text_chats_per_rolling_24h`).
- **VK-посты:** только `business_marketer_490`, месячный лимит `m4_business_marketer_max_vk_posts_per_month`.
- **Business free — картинки:** rolling 24h `m4_business_free_images_per_rolling_24h`.

## Водяной знак

Поле `generation_jobs.watermark_required` выставляется из `PlanEntitlements.watermark_on_image` при приёме заявки на картинку.

## Paywall

При отказе `EntitlementService` бот шлёт текст из `apps/bot/paywall.py` и клавиатуру с callback: подписка, пригласить друга, ввести код. Логика не в транспорте MAX — в `StateMachineService` + `EntitlementService`.

## Рефералы

- Код формата `R-XXXXXXXX`, выдаётся при первом запросе (`ReferralService.ensure_referral_code`).
- Привязка: меню «Ввести код приглашения» или кнопка в paywall.
- Награда **+3★** инвайтеру **один раз** на приглашённого, после первого события «картиночного» потока у приглашённого (`try_reward_on_first_image_flow`).
- Запрет самореферала и дубликатов — см. `packages/referrals/service.py` и `uq_referrals_invitee`.

## Звёзды (ledger)

Баланс = **SUM(`stars_ledger.delta`)**. Каждая строка содержит `reason`, `ref_type`, `ref_id`, `balance_after` (снимок после операции). См. `packages/stars/service.py`.

## Биллинг (заглушка Т-Банк)

Интерфейсы: `packages/billing/interfaces.py`, доменные объекты: `packages/billing/domain.py`, реализация-заглушка: `packages/billing/stub_service.py`.

- `create_checkout_session` — тестовая ссылка.
- `activate_subscription` — создаёт активную подписку; старые активные помечаются `superseded`. При повторном вызове с тем же `external_payment_id` в `meta` — **идемпотентный** возврат без второй строки.
- `cancel_subscription`, `handle_provider_webhook` — заглушки.

## Схема БД

Источник правды — **Alembic** (`alembic/versions/`). При старте API по умолчанию выполняется `upgrade head` (`run_alembic_on_startup=true`).

`create_all` из `init_db` включается только при `allow_runtime_create_all=true` (локальная отладка).

Переменная окружения `DATABASE_URL` перед миграцией выставляется в `apps/api/main.py` из настроек.

## Внутренние эндпоинты (отладка)

Требуют заголовок `X-Internal-Debug-Key`, совпадающий с `internal_debug_key` в `.env`. Если ключ не задан — проверка не пройдёт (404).

- `GET /internal/m4/summary?max_user_id=...` — план, квоты (счётчики), звёзды, рефералы, подписки.
- `POST /internal/m4/subscription/activate-stub` — тело `{"max_user_id": ..., "plan_code": "consumer_plus_290"}`. Использует фиксированный `external_payment_id=debug_stub` (повторный вызов идемпотентен).

## Локальные сценарии проверки

1. **Квота free:** три раза «Картинка» или «Поздравление» → четвёртый раз paywall.
2. **Подписка (stub):** `POST activate-stub` с `consumer_plus_290` → в summary `effective_plan_code` и лимиты месячные для картинок.
3. **Реферал:** пользователь A получает код в «Пригласить друга», B вводит код, B делает первую картинку/поздравление → у A +3★ одна строка в `stars_ledger`.
4. **Повтор webhook/активация:** дважды `activate-stub` для одного пользователя → одна подписка (см. тест идемпотентности).

## Тесты

```text
pip install -e ".[dev]"
pytest tests/test_m4.py -v
```

## Запуск API локально

```text
cd <корень репозитория>
pip install -e ".[dev]"
set DATABASE_URL=sqlite+aiosqlite:///./finalmaxbot.db
set INTERNAL_DEBUG_KEY=local-dev-key
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка: `GET http://127.0.0.1:8000/health` и `GET http://127.0.0.1:8000/internal/m4/summary?max_user_id=1` с заголовком `X-Internal-Debug-Key: local-dev-key`.
