# M3: примеры webhook и локальные команды

## Запуск API

Если в `.env` указан Postgres Supabase, но сеть/IPv6 недоступны, для локальной проверки задайте SQLite:

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./finalmaxbot.db"
```

```powershell
cd c:\FinalBotMax
python -m pip install -e ".[dev]"
# при смене схемы SQLite удалите старый файл БД:
Remove-Item .\finalmaxbot.db -ErrorAction SilentlyContinue
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
```

Проверка: `GET http://127.0.0.1:8765/health`

## Миграции (опционально, дублирует create_all)

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./finalmaxbot.db"
alembic upgrade head
```

## Автоматический прогон сценария

```powershell
python scripts\m3_webhook_simulate.py --base http://127.0.0.1:8765
```

## Пример: `bot_started`

```json
{
  "update_type": "bot_started",
  "timestamp": 1700000000,
  "user": { "user_id": 900001, "is_bot": false, "first_name": "Тест" }
}
```

```powershell
$body = Get-Content .\docs\samples\webhook_bot_started.json -Raw
Invoke-RestMethod -Uri "http://127.0.0.1:8765/webhooks/max" -Method Post -Body $body -ContentType "application/json; charset=utf-8"
```

## Пример: выбор режима consumer (v1)

```json
{
  "update_type": "message_callback",
  "timestamp": 1700000001,
  "callback": {
    "callback_id": "cb-mode-1",
    "payload": "v1|mode|consumer",
    "user": { "user_id": 900001, "is_bot": false }
  }
}
```

## Пример: кнопка «Задать вопрос»

```json
{
  "update_type": "message_callback",
  "timestamp": 1700000002,
  "callback": {
    "callback_id": "cb-ask-1",
    "payload": "v1|consumer|ask_question",
    "user": { "user_id": 900001, "is_bot": false }
  }
}
```

## Пример: текст вопроса (после `mid` для идемпотентности)

```json
{
  "update_type": "message_created",
  "timestamp": 1700000003,
  "message": {
    "sender": { "user_id": 900001, "is_bot": false, "first_name": "Тест" },
    "recipient": {},
    "timestamp": 1700000003,
    "body": { "mid": "m-900001-1", "text": "Что такое простыми словами ИИ?" }
  }
}
```

## Исходящие сообщения MAX (структура тела)

`POST https://platform-api.max.ru/messages?user_id=<id>`

```json
{
  "text": "Текст пользователю",
  "format": "markdown",
  "attachments": [
    {
      "type": "inline_keyboard",
      "payload": {
        "buttons": [
          [
            { "type": "callback", "text": "Для себя", "payload": "v1|mode|consumer" }
          ]
        ]
      }
    }
  ]
}
```

Ответ на callback: `POST /answers?callback_id=<id>` с телом `{ "notification": "Сохранено" }`.

## Проверка БД (SQLite)

```powershell
python -c "import sqlite3; c=sqlite3.connect('finalmaxbot.db'); print(c.execute('select max_user_id, current_mode from users').fetchall()); print(c.execute('select flow_state from conversations').fetchall()); print(c.execute('select kind from usage_events').fetchall()); print(c.execute('select status, prompt from generation_jobs').fetchall())"
```
