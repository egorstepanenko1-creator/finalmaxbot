from apps.bot.max_client import _normalize_max_upload_stage2_payload


def test_flat_token_passthrough() -> None:
    raw = {"token": "abc", "url": "https://x"}
    out = _normalize_max_upload_stage2_payload(raw)
    assert out == raw


def test_nested_photos_map() -> None:
    raw = {"photos": {"ph-99": {"token": "tok-1"}}}
    out = _normalize_max_upload_stage2_payload(raw)
    assert out is not None
    assert out["token"] == "tok-1"
    assert out["photo_id"] == "ph-99"


def test_nested_preserves_extra_meta() -> None:
    raw = {"photos": {"1": {"token": "t", "width": 100}}}
    out = _normalize_max_upload_stage2_payload(raw)
    assert out is not None
    assert out["token"] == "t"
    assert out["photo_id"] == "1"
    assert out["width"] == 100


def test_invalid_returns_none() -> None:
    assert _normalize_max_upload_stage2_payload({}) is None
    assert _normalize_max_upload_stage2_payload({"photos": {}}) is None
    assert _normalize_max_upload_stage2_payload({"photos": {"x": {}}}) is None
