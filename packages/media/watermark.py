"""Водяной знак на изображении (M5), без фиксированных размеров холста."""

from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def apply_watermark_if_needed(
    image_bytes: bytes,
    *,
    mime_type: str,
    watermark_required: bool,
    settings: Settings,
) -> tuple[bytes, dict[str, Any]]:
    """Возвращает (bytes, meta). Если знак не нужен — исходные байты."""
    meta: dict[str, Any] = {"watermark_applied": False, "input_mime": mime_type}
    if not watermark_required:
        return image_bytes, meta
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGBA")
        w, h = img.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text = settings.m5_watermark_text
        font = ImageFont.load_default()
        for name in ("arial.ttf", "DejaVuSans.ttf"):
            try:
                font = ImageFont.truetype(name, max(14, min(w, h) // 18))
                break
            except OSError:
                continue
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(6, min(w, h) // 40)
        x, y = w - tw - margin, h - th - margin
        alpha = int(255 * settings.m5_watermark_opacity)
        draw.text((x, y), text, fill=(255, 255, 255, alpha), font=font)
        combined = Image.alpha_composite(img, overlay)
        out = io.BytesIO()
        combined.convert("RGB").save(out, format="PNG", optimize=True)
        out_b = out.getvalue()
        meta["watermark_applied"] = True
        meta["watermark_text"] = text
        return out_b, meta
    except Exception:
        logger.exception("watermark_failed")
        meta["watermark_error"] = "apply_failed"
        return image_bytes, meta
