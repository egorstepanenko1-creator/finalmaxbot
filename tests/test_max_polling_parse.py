from apps.bot.max_polling import _extract_marker, _updates_list


def test_updates_list_top_level_array() -> None:
    assert _updates_list([{"update_type": "message_created"}]) == [{"update_type": "message_created"}]


def test_updates_list_updates_key() -> None:
    u = [{"a": 1}]
    assert _updates_list({"updates": u}) == u


def test_extract_marker_nested() -> None:
    assert _extract_marker({"marker": "m1"}, "old") == "m1"
    assert _extract_marker({"data": {"marker": "m2"}}, None) == "m2"
    assert _extract_marker({}, "keep") == "keep"
