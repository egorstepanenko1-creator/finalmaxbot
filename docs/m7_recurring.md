# M7: рекуррентные подписки и продление (Т-Банк)

## Что было в M6 и что изменилось

- **M6** по сути давал **разовую оплату** и выдавал доступ на фиксированный период (`m6_subscription_period_days`) без привязки карты для последующих списаний.
- **M7** добавляет **настоящую модель рекуррентного эквайринга Т-Банка** (Tinkoff Acquiring v2):
  1. **Родительский платёж (CC):** `Init` с `Recurrent=Y`, `CustomerKey`, `OperationInitiatorType=0` — покупатель оплачивает на форме, в уведомлении приходит **`RebillId`** (идентификатор сохранённых реквизитов, не PAN).
  2. **Дочерний платёж (MIT COF Recurring):** перед продлением периода бэкенд вызывает **`Init`** с `OperationInitiatorType=R` и затем **`Charge`** с `PaymentId` из ответа Init и **`RebillId`** из подписки.
  3. Продление периода в БД выполняется **после успешного webhook** по дочернему платежу (`DATA.billing_kind=subscription_renewal`).

Подключение рекуррентных списаний на терминале у Т-Банка должно быть **явно разрешено** (см. их сценарии «платежи по сохранённым реквизитам»).

## Состояния подписки (`subscription_state`)

| Состояние | Доступ по тарифу до `expires_at` |
|-----------|----------------------------------|
| `pending_activation` | Нет (бесплатный план) |
| `active` | Да |
| `renewal_due` | Да (списание инициировано) |
| `renewal_failed` | Да до конца текущего периода |
| `cancelled` | Да до конца периода (автопродление отключено) |
| `expired` | Нет |

Отмена (**кнопка «Отменить автопродление»**): `auto_renew_enabled=false`, состояние `cancelled`, **доступ сохраняется до `expires_at`**.

## Переменные окружения (дополнительно к M6)

| Переменная | Назначение |
|------------|------------|
| `M7_RECURRING_ENABLED` | `true` — первый checkout с `Recurrent=Y`; `false` — как разовая оплата без Rebill |
| `M7_RENEWAL_ADVANCE_HOURS` | За сколько часов до `expires_at` job может вызвать Init+Charge (по умолчанию 36) |

Остальные: `TBANK_*`, `M6_SUBSCRIPTION_PERIOD_DAYS`, `MAX_*` — как в M6.

## Webhook Т-Банка

- Маршрут: `POST /webhooks/tbank/notification`
- Первичная оплата: `DATA` содержит `billing_kind=subscription_initial` (или по умолчанию считается initial), `user_id`, `plan_code`, `customer_key`.
- Продление: `billing_kind=subscription_renewal`.
- Идемпотентность: по `PaymentId` в `billing_events`.
- Неуспех продления: `Success=false` + `subscription_renewal` → `renewal_failed`, уведомление в MAX.

## Фоновые задачи (in-process)

- **`python -m packages.billing.renewal_cli`**: помечает истёкшие подписки, шлёт в MAX текст об окончании доступа (если outbound включён), затем пытается **Init+Charge** для подписок в окне до истечения.
- Рекомендуется вызывать по **cron** (например, раз в час). Миграция на очередь — см. `docs/m6_launch.md` (техдолг).

## Admin / debug

`GET /internal/m7/subscription?max_user_id=...` с заголовком `X-Internal-Debug-Key: <INTERNAL_DEBUG_KEY>`:

- эффективный план;
- последние подписки (маскированный `RebillId`, флаги автопродления);
- последние `billing_events`.

## Smoke checklist (staging с публичными URL)

1. Заполнить `TBANK_*`, `TBANK_NOTIFICATION_URL` на `https://host/webhooks/tbank/notification`, `MAX_*`.
2. Поднять API с HTTPS, зарегистрировать webhook MAX на `POST /webhooks/max`.
3. Free-пользователь → paywall → оплата → webhook → в БД есть `tbank_rebill_id`, `subscription_state=active`.
4. Запустить `python -m packages.billing.renewal_cli` в окне до `expires_at` (или временно уменьшить `M7_RENEWAL_ADVANCE_HOURS` / период) → в логах `m7_event=renewal_charge_submitted`, после webhook — продлённый `expires_at`, событие `processed_renewal`.
5. «Отменить автопродление» → `cancelled`, CLI больше не шлёт Charge для этой подписки.
6. Следующая генерация до `expires_at` — платные entitlements.

**Живой E2E в этой среде не выполнялся** — проверка: `pytest tests/` (31 passed).

## Вне скоупа

Голос, видео, анимация, редактор фото; собственная PCI-форма; автоматическая сверка с `GetState` по всем `PaymentId`; полноценный DLQ/воркер.
