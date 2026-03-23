# M6: staging, MAX webhook, Т-Банк, подписки

## Staging и MAX

1. **Публичный HTTPS** для API (reverse proxy или туннель вроде ngrok/cloudflared).
2. **Переменные окружения** (см. `.env.example`):
   - `MAX_BOT_TOKEN` — токен бота MAX (staging/production).
   - `MAX_WEBHOOK_SECRET` — секрет проверки входящих webhook MAX.
   - `MAX_OUTBOUND_ENABLED=true` — исходящие ответы бота (можно `false` для «только приём»).
3. **Подписка webhook в MAX** (по документации платформы MAX):
   - URL: **`POST https://<ваш-хост>/webhooks/max`** (`apps/bot/router.py`).
   - Заголовок / секрет — как требует MAX; в коде проверяется заголовок `X-Max-Bot-Api-Secret` на равенство `MAX_WEBHOOK_SECRET`, если он задан.
   - Указать тот же секрет, что в `MAX_WEBHOOK_SECRET`.
4. При старте API вызывается `warn_launch_readiness()`: предупреждения в лог, если нет токена при включённом outbound, пустой webhook secret, неполная конфигурация Т-Банка.

## Т-Банк (эквайринг)

| Переменная | Назначение |
|------------|------------|
| `TBANK_TERMINAL_KEY` | TerminalKey терминала |
| `TBANK_PASSWORD` | Пароль терминала (для подписи Init и проверки уведомлений) |
| `TBANK_API_BASE` | По умолчанию `https://securepay.tinkoff.ru/v2` |
| `TBANK_NOTIFICATION_URL` | Публичный URL колбэка **полностью**, например `https://host/webhooks/tbank/notification` |
| `TBANK_SUCCESS_URL` | Опционально: редирект после оплаты |
| `TBANK_PAYMENT_DESCRIPTION_PREFIX` | Префикс описания платежа |
| `TBANK_SKIP_SIGNATURE_VERIFY` | `true` только в локальной отладке (не в production) |
| `M6_SUBSCRIPTION_PERIOD_DAYS` | Длительность подписки после оплаты (по умолчанию 30) |

Без `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD` используется **stub-биллинг** (тестовые ссылки).

## Billing webhook (контракт)

- **Маршрут:** **`POST /webhooks/tbank/notification`** (`apps/api/billing_webhook.py`)
- **Тело:** JSON уведомления Acquiring (поля `Success`, `Status`, `PaymentId`, `OrderId`, `DATA`, `Token`, …).
- **OrderId:** формат `fm_{internal_user_id}_{uuid}` — резервный способ узнать пользователя.
- **DATA:** JSON-строка с полями `user_id` (внутренний id в БД) и `plan_code` (`consumer_plus_290`, `business_marketer_490`, `stars_topup_99`).
- **Идемпотентность:** по `PaymentId` в таблице `billing_events` (`idempotency_key` unique). Повторный колбэк не активирует подписку повторно.
- **Ответ:** `{"OK": true}` (HTTP 200).

Секреты в лог не пишутся; в БД сохраняется `payload_safe` (поле `Token` замаскировано).

## Модель подписки

- Таблица `subscriptions`: `user_id`, `plan_code`, `status` (`active`, `superseded`, `cancelled`, …), `expires_at`, `meta` (в т.ч. `external_payment_id` для идемпотентности активации).
- Эффективный план: `packages/entitlements/resolver.py` — последняя **active** запись с планом plus/marketer; если `expires_at` в прошлом — откат к `consumer_free` / `business_free` по режиму.

## Технический долг (операционная безопасность)

- **Фоновые задачи сейчас in-process:** после успешного billing webhook подтверждение в MAX ставится через `asyncio.create_task` без отдельной очереди.
- **Путь миграции:** вынести отправку в MAX в очередь (Redis/RQ, Celery, cloud tasks) с ретраями и DLQ; граница уже узкая — `MaxBotClient.send_message` после активации.

## Smoke checklist (staging)

1. Пользователь на free упирается в paywall (лимит картинки/вопроса).
2. Кнопки «Для себя — 290 ₽» / «Бизнес — 490 ₽» открывают сообщение со ссылкой Т-Банка.
3. Тестовая оплата → webhook → в БД `billing_events` с `outcome=processed`, активная `subscriptions` с нужным `plan_code`.
4. Повторный webhook с тем же `PaymentId` → в логах `m6_event=billing_callback_deduplicated`, без второй активной подписки.
5. Следующее действие (картинка / VK) проходит без free-ограничения в рамках плана.
6. В MAX приходит текст успешной оплаты (если настроены токен и outbound).

## Вне скоупа M6

Голос, видео, анимация, редактор фото — не подключались.
