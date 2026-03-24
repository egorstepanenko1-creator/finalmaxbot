# Runbook запуска (MAX + Т-Банк)

## Smoke: MAX (бот)

1. Открыть диалог с ботом, убедиться в `WELCOME` и кнопках режима.
2. **Для меня** → два сообщения: объяснение режима + быстрый старт; меню consumer.
3. **Для бизнеса** → аналогично для business.
4. **Шаблоны** / **Шаблоны постов** → заголовок меню, выбор пункта → черновик + подсказка отправить одним сообщением.
5. Потоки без оплаты (в пределах лимита): вопрос, картинка, поздравление (consumer); пост VK и картинка (business) — корректные промпты на русском.
6. Paywall при исчерпании лимита — тексты из paywall, кнопки подписки / реферал / код.
7. **Подписка** → текст про оплату + ссылка (stub или Т-Банк в зависимости от окружения).
8. **Отменить автопродление** при отсутствии платной подписки → `NO_AUTORENEW_TO_CANCEL`.

## Smoke: Т-Банк (после выдачи терминала)

1. `TBANK_*` / webhook URL в настройках совпадают с кабинетом банка.
2. Тестовая оплата подписки consumer → в БД активная подписка, `NOTICE_PAYMENT_SUCCESS_CONSUMER` в MAX.
3. Тестовая оплата business → `NOTICE_PAYMENT_SUCCESS_BUSINESS`.
4. Webhook `CONFIRMED` / статусы: запись в `BillingEvent`, корректный `subscription_state`.
5. (Staging) отключение подписи webhook → логи API, нет 500 на `/billing/webhook`.

## После первой успешной оплаты

- В операторской сводке: `effective_plan_code`, активная подписка, `expires_at`, `auto_renew_enabled`, маскированный RebillId.
- В MAX: сообщение об успешной оплате; меню открывает платные действия без лишнего paywall.

## После первой платной генерации

- Списание квоты / usage: новая запись в `usage_events` (сводка в `/internal/launch/user` или CLI).
- Картинка без водяного знака (если тариф так предусматривает).

## Типичные сбои и куда смотреть

| Симптом | Где смотреть |
|---------|----------------|
| Нет ответа в MAX | Логи воркера бота, `max_outbound_enabled`, токен MAX |
| «Ссылка недоступна» | `PAYMENT_LINK_UNAVAILABLE` — логи `create_checkout_session`, ключи Т-Банка |
| Оплата прошла, подписки нет | Логи webhook, `BillingEvent`, идемпотентность по `OrderId` / `PaymentId` |
| Продление не списалось | `NOTICE_RENEWAL_FAILED`, `subscription_state`, `renewal_cli` / логи Charge |
| Доступ не снялся после expiry | `renewal_cli`, `mark_subscription_expired`, `notice_access_expired` |

## Операторская сводка

- HTTP: `GET /internal/launch/user?max_user_id=<id>` с заголовком `X-Internal-Debug-Key: <INTERNAL_DEBUG_KEY>`.
- CLI: `python -m packages.ops.operator_cli <max_user_id>` (те же данные из БД, ключ не нужен — доступ к БД = доверенная зона).
