"""Small, deterministic language policy for generated asset prose."""

from __future__ import annotations

from typing import Literal

AssetLanguage = Literal["zh", "en", "source"]


def detect_asset_language(text: str) -> AssetLanguage:
    """Choose Chinese or English from the dominant script in ``text``.

    Chinese and English are the languages this contract formally classifies.
    Japanese kana and Korean Hangul select ``source`` so those projects are
    never explicitly translated to Chinese. Ties and empty input retain the
    historical Chinese default.
    """
    han = 0
    latin = 0
    for character in str(text or ""):
        codepoint = ord(character)
        if (
            0x3040 <= codepoint <= 0x30FF
            or 0x1100 <= codepoint <= 0x11FF
            or 0x3130 <= codepoint <= 0x318F
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            return "source"
        if 0x3400 <= codepoint <= 0x4DBF or 0x4E00 <= codepoint <= 0x9FFF:
            han += 1
        elif "A" <= character <= "Z" or "a" <= character <= "z":
            latin += 1
    return "zh" if han >= latin else "en"


def asset_language_instruction(language: AssetLanguage) -> str:
    """Return the shared language rule appended to model requests."""
    if language == "en":
        return (
            "Write every user-visible prose field in English. "
            "Keep every supplied character and location name verbatim; "
            "never translate, romanize, or rewrite a name."
        )
    if language == "source":
        return (
            "Write every user-visible prose field in the same dominant natural "
            "language as the supplied source text. Keep every supplied character "
            "and location name verbatim; never translate, romanize, or rewrite a name."
        )
    return (
        "所有面向用户的自由文本字段都使用中文。"
        "人物名和地点名必须按输入原样保留，不得翻译、音译或改写。"
    )
