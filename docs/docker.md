# Docker: сборка и запуск API / бота MAX

Секреты и конфигурация **только через переменные окружения** в рантайме (или `.env` для compose). В образ не кладутся токены и локальные `.db`.

## Образ

- Python 3.12-slim, установка пакета из `pyproject.toml`.
- Миграции Alembic на Postgres идут через **синхронный** драйвер `psycopg2-binary` (в `pyproject.toml`); рантайм приложения — `asyncpg` по `DATABASE_URL` с `postgresql+asyncpg://`.
- На старте: `alembic upgrade head`, если `RUN_ALEMBIC_ON_STARTUP=true` (по умолчанию в приложении — `true`).
- Генерированные файлы: каталог `M5_LOCAL_STORAGE_ROOT` (в compose по умолчанию `/data/generated`) — **монтируйте volume**, иначе после перезапуска контейнера файлы пропадут.
- `DATABASE_URL` в формате async: `postgresql+asyncpg://user:pass@host:5432/dbname` (Supabase / Neon / RDS — без правок кода).

## Сборка

Из корня репозитория:

```bash
docker build -t finalmaxbot:latest .
```

## Запуск только приложения (внешняя БД)

Задайте `DATABASE_URL` в файле `.env` в корне проекта (compose подставит его в сервис) **или** экспортируйте в shell:

```bash
export DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME"
docker compose up --build -d
```

Проверка:

```bash
curl -sS http://127.0.0.1:8000/health
# {"status":"ok"}
```

Остановка:

```bash
docker compose down
```

Том `media_data` сохраняет содержимое `/data/generated` между перезапусками (`docker compose down` **без** `-v` не удаляет named volume).

## Запуск с локальным Postgres (dev / staging)

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build -d
```

Пароль БД: переменная `POSTGRES_PASSWORD` (по умолчанию в override — слабый dev-пароль, смените).

`app` ждёт healthy `postgres` (через `depends_on`); дополнительно entrypoint ждёт TCP к хосту из `DATABASE_URL`.

## Полезные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://...`) |
| `RUN_ALEMBIC_ON_STARTUP` | `true` / `false` — миграции при старте приложения |
| `M5_LOCAL_STORAGE_ROOT` | Каталог медиа (в образе по умолчанию `/data/generated`) |
| `MAX_BOT_TOKEN`, `MAX_API_BASE`, `MAX_WEBHOOK_SECRET` | MAX API |
| `MAX_OUTBOUND_ENABLED` | `false` — без исходящих в MAX (удобно для smoke без токена) |
| `INTERNAL_DEBUG_KEY` | Внутренние `/internal/*` эндпоинты |
| `TBANK_*` | Эквайринг (см. `packages/shared/settings.py`) |
| `YANDEX_*` | LLM / картинки (опционально) |
| `DB_WAIT_TIMEOUT_SEC` | Таймаут ожидания TCP БД в entrypoint (сек), по умолчанию 90 |

Полный список полей: `packages/shared/settings.py` (имена в ENV в `UPPER_SNAKE_CASE`).

## Команды проверки устойчивости медиа

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.postgres.yml exec app sh -c 'echo probe > /data/generated/persistence_probe.txt'
docker compose -f docker-compose.yml -f docker-compose.postgres.yml restart app
docker compose -f docker-compose.yml -f docker-compose.postgres.yml exec app cat /data/generated/persistence_probe.txt
```

Ожидается содержимое `probe` после рестарта.

## Healthcheck

В `Dockerfile` и в `docker-compose.yml` для сервиса `app`: HTTP GET `http://127.0.0.1:8000/health`.

## Порт

По умолчанию `8000` наружу; переопределение: `APP_PORT=8080 docker compose up -d`.
