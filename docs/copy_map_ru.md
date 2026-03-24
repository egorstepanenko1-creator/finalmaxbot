# Карта пользовательских текстов (RU)

Единый источник: `packages/shared/user_copy_ru.py`. Ниже — где что используется.

| Константа | Назначение |
|-----------|------------|
| `WELCOME` | Первое сообщение в боте |
| `MODE_SELECT_NUDGE` | Подсказка выбора режима |
| `AFTER_MODE_CONSUMER` / `AFTER_MODE_BUSINESS` | Текст сразу после выбора «Для меня» / «Для бизнеса» |
| `FIRST_ACTIONS_*_HINT` | Строка над быстрыми кнопками после режима |
| `CONSUMER_GUIDANCE_SHORT` / `BUSINESS_GUIDANCE_SHORT` | Краткие подсказки по меню |
| `ASK_QUESTION_PROMPT` | Вход в поток «вопрос» |
| `CREATE_IMAGE_*_PROMPT` | Запрос описания картинки (consumer / business) |
| `GREETING_PROMPT` | Запрос данных для поздравления |
| `VK_POST_PROMPT` | Запрос текста для поста VK |
| `IDLE_CHOOSE_BUTTONS` | Напоминание пользоваться кнопками |
| `REFERRAL_CODE_PROMPT` / `REFERRAL_CODE_EMPTY` | Ввод кода приглашения |
| `REFERRAL_MESSAGES` | Ответы на ввод рефкода |
| `STARS_*` | Баланс звёзд |
| `NO_AUTORENEW_TO_CANCEL` | Нет подписки для отмены автопродления |
| `PAYMENT_LINK_UNAVAILABLE` | Нет ссылки на оплату |
| `PAYWALL_*` | Лимиты и paywall (`apps/bot/paywall.py`) |
| `SUBSCRIPTION_UX_STUB` / `SUBSCRIPTION_UX_LIVE` | Текст перед ссылкой (stub / T-Bank) |
| `INVITE_FRIEND_UX` | Экран «пригласить друга» |
| `NOTICE_PAYMENT_SUCCESS_*` | Успешная первая оплата по тарифу |
| `NOTICE_SUBSCRIPTION_RENEWED` | Успешное продление |
| `NOTICE_RENEWAL_FAILED` | Срыв списания за продление |
| `NOTICE_FIRST_PAYMENT_FAILED` | Первая оплата не прошла |
| `NOTICE_AUTORENEW_CANCELLED` | Автопродление отключено |
| `NOTICE_SUBSCRIPTION_EXPIRED` | Подписка истекла (и уведомление из renewal job) |
| `TEMPLATES_MENU_TITLE_*` | Заголовки меню шаблонов |
| `WORKING_GREETING` / `WORKING_VK` | «Ждите, готовлю…» |
| `TEMPLATE_FOLLOWUP` | Показ черновика после выбора шаблона |

Биллинг-обёртки: `packages/billing/max_notices.py` → те же `NOTICE_*`.
