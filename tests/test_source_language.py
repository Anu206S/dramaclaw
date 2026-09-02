import pytest

from novelvideo.utils.source_language import (
    asset_language_instruction,
    detect_asset_language,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("第一场 客厅 日 内\n林默推开门。", "zh"),
        ("INT. LIVING ROOM - DAY\nMAYA opens the door.", "en"),
        ("ABC门打开", "zh"),
        ("第一話\n図書館で美咲が本を開く。", "source"),
        ("제1화\n도서관에서 민지가 책을 펼친다.", "source"),
        ("", "zh"),
    ],
)
def test_detect_asset_language_uses_the_dominant_script(source, expected):
    assert detect_asset_language(source) == expected


def test_english_instruction_keeps_prose_english_and_names_verbatim():
    instruction = asset_language_instruction("en")

    assert "English" in instruction
    assert "verbatim" in instruction


def test_chinese_instruction_keeps_prose_chinese_and_names_unchanged():
    instruction = asset_language_instruction("zh")

    assert "中文" in instruction
    assert "原样" in instruction


def test_other_scripts_are_told_to_follow_the_source_without_translation():
    instruction = asset_language_instruction("source")

    assert "same dominant natural language" in instruction
    assert "verbatim" in instruction
