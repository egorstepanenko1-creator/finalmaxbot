# API + webhook MAX (FastAPI / Uvicorn). Секреты только через env в рантайме.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY apps /app/apps
COPY packages /app/packages
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh

RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && pip install --upgrade pip \
    && pip install .

# Локальное хранилище сгенерированных медиа (монтируйте volume на этот путь)
ENV M5_LOCAL_STORAGE_ROOT=/data/generated
RUN mkdir -p /data/generated \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data/generated

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=50s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
