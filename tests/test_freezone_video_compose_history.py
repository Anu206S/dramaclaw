from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from novelvideo.freezone.history import read_generation_history
from novelvideo.task_backend.runners import freezone as freezone_runner


@pytest.mark.asyncio
async def test_video_compose_runner_records_node_generation_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "freezone" / "_outputs" / "freezone_video_compose" / "job-a.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"video")

    async def fake_compose(**_kwargs):
        return output

    monkeypatch.setattr("novelvideo.freezone.jobs.run_freezone_video_compose", fake_compose)
    monkeypatch.setattr(freezone_runner, "_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "novelvideo.api.deps.make_static_url_for_context",
        lambda _ctx, relative: f"/static/project/{relative}",
    )
    ctx = SimpleNamespace(project_id="project-a", output_dir=str(tmp_path))
    envelope = {
        "payload": {
            "job_id": "job-a",
            "project_dir": str(tmp_path),
            "canvas_id": "canvas-a",
            "node_id": "compose-a",
            "tracks": [],
        }
    }

    result = await freezone_runner._run_freezone_video_compose_async(envelope, ctx)

    assert result["output_url"].endswith("job-a.mp4")
    records = read_generation_history(
        project_dir=tmp_path,
        canvas_id="canvas-a",
        node_id="compose-a",
    )
    assert len(records) == 1
    assert records[0]["task_type"] == "freezone_video_compose"
    assert records[0]["media_type"] == "video"
    assert records[0]["result"]["output_url"].endswith("job-a.mp4")
