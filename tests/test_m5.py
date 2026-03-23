"""M5: текст, картинки, водяной знак, квота при успехе, приветственный сценарий."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from apps.bot.generation_orchestrator import GenerationOrchestrator
from packages.db.models import GenerationJob, StoredFile, UsageEvent, User
from packages.domain.image_generation import ImageGenerationResult
from packages.domain.text_generation import TextGenerationOutput
from packages.media.watermark import apply_watermark_if_needed
from packages.providers.image_generation import StubPillowImageProvider
from packages.providers.text_generation import StubTextGenerationProvider
from packages.shared.settings import Settings
from packages.storage.local import LocalFileStorage


class OkTextStub:
    async def generate(self, *, system_prompt: str, user_prompt: str) -> TextGenerationOutput:
        return TextGenerationOutput(
            text="Тёплое тестовое поздравление для вас. Здоровья и радости!",
            ok=True,
            provider="stub",
        )


class FailTextStub:
    async def generate(self, *, system_prompt: str, user_prompt: str) -> TextGenerationOutput:
        return TextGenerationOutput(text="Сервис недоступен.", ok=False, provider="stub", error_code="x")


class FailImageProvider:
    async def generate(self, *, prompt: str, correlation_id: str, meta: dict | None = None):
        _ = (prompt, correlation_id, meta)
        return ImageGenerationResult(
            ok=False,
            image_bytes=None,
            mime_type="image/png",
            provider="fail",
            error_code="forced_fail",
        )


class RecordingClient:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.images: list[dict] = []

    async def send_message(self, *, user_id: int, text: str, attachments=None, fmt=None) -> bool:
        _ = (user_id, attachments, fmt)
        self.texts.append(text)
        return True

    async def send_message_with_image(self, **kwargs) -> bool:
        self.images.append(kwargs)
        return True


@pytest.fixture
def m5_settings(tmp_path) -> Settings:
    return Settings(
        m5_local_storage_root=str(tmp_path / "m5data"),
        run_alembic_on_startup=False,
        allow_runtime_create_all=False,
    )


async def test_stub_text_generation_output() -> None:
    t = StubTextGenerationProvider()
    o = await t.generate(system_prompt="s", user_prompt="привет")
    assert o.ok is True
    assert "stub" in o.text.lower() or "запрос" in o.text.lower()


async def test_watermark_only_when_required(m5_settings: Settings) -> None:
    prov = StubPillowImageProvider(m5_settings)
    r = await prov.generate(prompt="x", correlation_id="cid", meta=None)
    assert r.ok and r.image_bytes
    b_on, m_on = apply_watermark_if_needed(
        r.image_bytes,
        mime_type=r.mime_type,
        watermark_required=True,
        settings=m5_settings,
    )
    assert m_on.get("watermark_applied") is True
    b_off, m_off = apply_watermark_if_needed(
        r.image_bytes,
        mime_type=r.mime_type,
        watermark_required=False,
        settings=m5_settings,
    )
    assert m_off.get("watermark_applied") is False
    assert len(b_on) > 0 and len(b_off) > 0


async def test_image_job_success_creates_usage_and_stored_file(
    session_factory, m5_settings: Settings
) -> None:
    storage_root = m5_settings.m5_local_storage_root
    orch = GenerationOrchestrator(
        settings=m5_settings,
        session_factory=session_factory,
        text_port=OkTextStub(),
        image_port=StubPillowImageProvider(m5_settings),
        storage=LocalFileStorage(storage_root),
    )
    async with session_factory() as s:
        u = User(max_user_id=101, current_mode="consumer", onboarding_state="x")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        job = GenerationJob(
            user_id=u.id,
            conversation_id=None,
            feature_type="image",
            status="queued",
            prompt="тестовая картинка",
            watermark_required=False,
            correlation_id="corr-1",
            context_kind="consumer_image",
        )
        s.add(job)
        await s.commit()
        jid = job.id
    rc = RecordingClient()
    await orch.run_image_job_after_commit(jid, 101, rc)
    async with session_factory() as s:
        cnt = (await s.execute(select(func.count()).select_from(UsageEvent))).scalar_one()
        assert int(cnt) == 1
        sf = (await s.execute(select(StoredFile).where(StoredFile.generation_job_id == jid))).scalar_one()
        assert sf.byte_size > 0
        j = await s.get(GenerationJob, jid)
        assert j is not None and j.status == "succeeded"


async def test_image_job_failure_no_usage(session_factory, m5_settings: Settings) -> None:
    orch = GenerationOrchestrator(
        settings=m5_settings,
        session_factory=session_factory,
        text_port=OkTextStub(),
        image_port=FailImageProvider(),
        storage=LocalFileStorage(m5_settings.m5_local_storage_root),
    )
    async with session_factory() as s:
        u = User(max_user_id=102, current_mode="consumer", onboarding_state="x")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        job = GenerationJob(
            user_id=u.id,
            feature_type="image",
            status="queued",
            prompt="x",
            watermark_required=False,
            correlation_id="c2",
            context_kind="consumer_image",
        )
        s.add(job)
        await s.commit()
        jid = job.id
    await orch.run_image_job_after_commit(jid, 102, RecordingClient())
    async with session_factory() as s:
        cnt = (await s.execute(select(func.count()).select_from(UsageEvent))).scalar_one()
        assert int(cnt) == 0
        j = await s.get(GenerationJob, jid)
        assert j is not None and j.status == "failed"


async def test_greeting_bundle_finalizes_text_greeting_usage(session_factory, m5_settings: Settings) -> None:
    orch = GenerationOrchestrator(
        settings=m5_settings,
        session_factory=session_factory,
        text_port=OkTextStub(),
        image_port=StubPillowImageProvider(m5_settings),
        storage=LocalFileStorage(m5_settings.m5_local_storage_root),
    )
    async with session_factory() as s:
        u = User(max_user_id=103, current_mode="consumer", onboarding_state="x")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id
    await orch.run_greeting_bundle_after_commit(
        max_user_id=103,
        internal_user_id=uid,
        conversation_id=None,
        raw_prompt="маме на день рождения",
        wm_required=False,
        client=RecordingClient(),
        followup_menu=None,
    )
    async with session_factory() as s:
        rows = (await s.execute(select(UsageEvent))).scalars().all()
        kinds = [r.kind for r in rows]
        assert "text_greeting" in kinds


async def test_fail_text_no_greeting_usage(session_factory, m5_settings: Settings) -> None:
    orch = GenerationOrchestrator(
        settings=m5_settings,
        session_factory=session_factory,
        text_port=FailTextStub(),
        image_port=StubPillowImageProvider(m5_settings),
        storage=LocalFileStorage(m5_settings.m5_local_storage_root),
    )
    async with session_factory() as s:
        u = User(max_user_id=104, current_mode="consumer", onboarding_state="x")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id
    await orch.run_greeting_bundle_after_commit(
        max_user_id=104,
        internal_user_id=uid,
        conversation_id=None,
        raw_prompt="тест",
        wm_required=False,
        client=RecordingClient(),
        followup_menu=None,
    )
    async with session_factory() as s:
        cnt = (await s.execute(select(func.count()).select_from(UsageEvent))).scalar_one()
        assert int(cnt) == 0
