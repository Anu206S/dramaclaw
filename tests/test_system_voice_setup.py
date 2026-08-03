from pathlib import Path

import pytest

from novelvideo.models import NovelCharacter


class _FakeStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.characters = [
            NovelCharacter(name="林夏", gender="女", age_group="youth", is_main=True)
        ]
        self.beats = [
            {
                "beat_number": 1,
                "audio_type": "narration",
                "narration_segment": "夜色笼罩着城市。",
            },
            {
                "beat_number": 2,
                "audio_type": "dialogue",
                "speaker": "林夏_日常",
                "narration_segment": "“我们出发吧。”",
            },
        ]

    async def get_beats_as_dicts(self, episode: int):
        assert episode == 1
        return self.beats

    async def list_characters(self):
        return self.characters

    async def update_character(self, name: str, **updates):
        character = next(item for item in self.characters if item.name == name)
        for key, value in updates.items():
            setattr(character, key, value)


@pytest.mark.asyncio
async def test_prepare_missing_system_voices_fills_narrator_and_character(
    monkeypatch,
    tmp_path,
):
    from novelvideo.audio import indextts2_beat_audio_task
    from novelvideo.audio import system_voice_setup
    from novelvideo.generators.tts_generator import TTSResult

    narrator_updates: list[dict] = []

    class FakeEdgeTTSGenerator:
        def __init__(self, voice: str) -> None:
            self.voice = voice

        async def generate(self, *, text, output_path, generate_subtitle):  # noqa: ARG002
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"audio:{self.voice}".encode())
            return TTSResult(success=True, audio_path=str(path))

    async def no_remaining_errors(**kwargs):  # noqa: ARG001
        return []

    monkeypatch.setattr(system_voice_setup, "EdgeTTSGenerator", FakeEdgeTTSGenerator)
    monkeypatch.setattr(
        system_voice_setup,
        "load_effective_narration_style_for_voice",
        lambda username, project: "third_person",
    )
    monkeypatch.setattr(
        system_voice_setup,
        "load_narrator_reference_audio",
        lambda username, project: {"path": ""},
    )
    monkeypatch.setattr(
        system_voice_setup,
        "set_narrator_reference_audio",
        lambda username, project, **kwargs: narrator_updates.append(kwargs),
    )
    monkeypatch.setattr(
        indextts2_beat_audio_task,
        "collect_indextts2_voice_prereq_errors",
        no_remaining_errors,
    )
    store = _FakeStore(tmp_path)

    result = await system_voice_setup.prepare_missing_system_voices(
        store=store,
        username="alice",
        project="demo",
        project_dir=tmp_path,
        episode=1,
    )

    assert result["ready"] is True
    assert result["prepared_count"] == 2
    assert {item["target"] for item in result["prepared"]} == {"项目解说人", "林夏"}
    assert narrator_updates[0]["relative_path"] == "assets/narrator/voice.mp3"
    assert store.characters[0].reference_audio_path
    assert (tmp_path / store.characters[0].reference_audio_path).exists()
