# M5: пайплайн выдачи (текст, картинки, MAX, квоты)

## Обзор

После M4 квоты **финализируются в момент успешной генерации и сохранения результата**, а не в момент нажатия кнопки (кроме текстового вопроса — см. ниже).

## Текст (Yandex / stub)

- Контракт: `TextGenerationPort.generate(...) -> TextGenerationOutput` (`packages/domain/text_generation.py`).
- Реализации: `StubTextGenerationProvider`, `YandexFoundationTextProvider` (`packages/providers/text_generation.py`).
- Режим Yandex: задайте `YANDEX_CLOUD_API_KEY` и `YANDEX_FOLDER_ID`.
- При `ok=False` пользователю показывается `text` (дружелюбная ошибка), **квота не списывается** (для сценариев «вопрос» и фоновых пакетов).

## Картинки

- Порт: `ImageGenerationPort` (`packages/providers/image_generation.py`).
- **Stub:** `StubPillowImageProvider` — локальный PNG (градиент + фрагмент промпта).
- **Yandex Art (async):** включите `YANDEX_IMAGE_GENERATION_ENABLED=true` при тех же ключе и каталоге, что и для текста. URL и шаблон операции настраиваются в `Settings` (`yandex_image_async_url`, `yandex_image_operations_url_template`, интервалы опроса).
- Жизненный цикл `generation_jobs.status`: `queued` → `processing` → `succeeded` | `failed`.
- В `provider_meta` попадают только **безопасные** поля (без секретов).

## Хранилище файлов

- Интерфейс: `FileStoragePort` (`packages/storage/interface.py`).
- Локально: `LocalFileStorage` в каталоге `M5_LOCAL_STORAGE_ROOT` (по умолчанию `./data/generated`).
- Метаданные: таблица `stored_files` (связь 1:1 с `generation_jobs`).

## Водяной знак

- Политика: `watermark_required` на задании (из entitlements плана).
- Реализация: `apply_watermark_if_needed` (`packages/media/watermark.py`), текст и прозрачность из настроек: `M5_WATERMARK_TEXT`, `M5_WATERMARK_OPACITY`.
- В `stored_files.meta` пишется `watermark_applied` и связанные поля.

## MAX: исходящие сообщения

1. **Только текст:** `POST /messages` с телом `{"text": "...", "format": "markdown"}` (опционально).
2. **Картинка:** `POST /uploads?type=image` → загрузка по выданному `url` (multipart `data`) → `token` в ответе → `POST /messages` с  
   `attachments: [{"type": "image", "payload": {"token": "<token>"}}]`.
3. **Текст + картинка:** два шага или одно сообщение с `text` + `attachments` (используется в поздравлении и VK: сначала текст поста/поздравления, затем изображение с подписью).

Повторы отправки при `attachment.not.ready`: см. `m5_max_send_attachment_retries` и паузу `m5_max_upload_ready_delay_sec`.

## Поздравление и VK

- **Поздравление:** намерение (`birthday` / `anniversary` / `holiday` / `universal`) — эвристики в `packages/greeting/intents.py`. Фоновая задача: текст → задание на картинку → доставка текста и открытки.
- **VK:** фоновый пакет — текст поста + промпт картинки из текста поста + иллюстрация.

## Политика квот (M5)

| Сценарий | Резерв | Финализация | При ошибке картинки |
|----------|--------|-------------|---------------------|
| Вопрос (ask_question) | — | `UsageEvent` после `ok=True` | Нет списания при `ok=False` |
| Картинка (кнопка) | — | `consumer_image_intake` / `business_image_intake` после `succeeded` | Нет `UsageEvent`; пользователю сообщение об ошибке |
| Поздравление | — | `text_greeting` после успеха картинки | Текст может быть показан, квота **не** списывается |
| Пост VK | — | `text_vk_post` после успеха картинки | Текст поста может быть показан, квота **не** списывается |

## Фоновые задачи

- Задачи планируются **после** `commit` транзакции webhook: список колбэков в `apps/bot/router.py` → `asyncio.create_task`.
- Замена на очередь (Redis, YMQ): обернуть вызовы оркестратора в продюсер задач.

## Логи (корреляция)

Префикс событий: `m5_event=...`, поля `job_id`, `correlation_id`, `context_kind` где применимо.

## Локальный запуск

```bash
pip install -e ".[dev]"
set DATABASE_URL=sqlite+aiosqlite:///./finalmaxbot.db
set YANDEX_CLOUD_API_KEY=...
set YANDEX_FOLDER_ID=...
# опционально картинки Yandex Art:
set YANDEX_IMAGE_GENERATION_ENABLED=true
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Тесты:

```bash
pytest tests/test_m5.py tests/test_m4.py -v
```

## Сценарии проверки UX

1. **Free consumer + картинка:** тариф `consumer_free` → в `stored_files.meta` `watermark_applied=true`.
2. **Paid consumer:** подписка `consumer_plus_290` → `watermark_required=false` на job → без водяного знака.
3. **Поздравление:** после ответа — два сообщения: текст поздравления и картинка.
