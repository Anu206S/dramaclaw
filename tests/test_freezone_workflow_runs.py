from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from novelvideo.freezone.workflow_runs import (
    create_workflow_run,
    interrupt_stale_workflow_runs,
    list_workflow_runs,
    read_workflow_run,
    reconcile_workflow_runs_with_canvas_nodes,
    update_workflow_run,
)


def test_workflow_run_tracks_actions_and_completion(tmp_path: Path) -> None:
    run = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[
            {"node_id": "image-1", "action": "generate_image"},
            {"node_id": "video-1", "action": "generate_video"},
        ],
        actor_id="alice",
    )

    updated = update_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=run["run_id"],
        action_updates=[
            {"node_id": "image-1", "action": "generate_image", "status": "completed"},
            {"node_id": "video-1", "action": "generate_video", "status": "blocked"},
        ],
        status="failed",
    )

    assert updated is not None
    assert updated["status"] == "failed"
    assert updated["resumable"] is True
    assert updated["completed_at"]
    assert [item["status"] for item in updated["actions"]] == ["completed", "blocked"]
    assert read_workflow_run(
        project_dir=tmp_path, canvas_id="default", run_id=run["run_id"]
    ) == updated


def test_workflow_runs_are_listed_newest_first(tmp_path: Path) -> None:
    first = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "one", "action": "generate_image"}],
    )
    second = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "two", "action": "generate_video"}],
    )

    listed = list_workflow_runs(project_dir=tmp_path, canvas_id="default")

    assert [item["run_id"] for item in listed] == [second["run_id"], first["run_id"]]


def test_new_workflow_run_supersedes_overlapping_resumable_run(tmp_path: Path) -> None:
    first = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[
            {"node_id": "shared", "action": "generate_image"},
            {"node_id": "old-only", "action": "generate_video"},
        ],
    )
    second = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "shared", "action": "generate_image"}],
    )

    superseded = read_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=first["run_id"],
    )
    assert superseded is not None
    assert superseded["status"] == "cancelled"
    assert superseded["resumable"] is False
    assert superseded["metadata"]["superseded_by_run_id"] == second["run_id"]

    stale_update = update_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=first["run_id"],
        status="completed",
    )
    assert stale_update is not None
    assert stale_update["status"] == "cancelled"


def test_new_workflow_run_supersedes_disjoint_active_run_on_same_canvas(tmp_path: Path) -> None:
    first = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "one", "action": "generate_image"}],
    )
    create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "two", "action": "generate_video"}],
    )

    preserved = read_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=first["run_id"],
    )
    assert preserved is not None
    assert preserved["status"] == "cancelled"
    assert preserved["resumable"] is False


def test_reconcile_cancels_run_after_all_unfinished_nodes_are_deleted(tmp_path: Path) -> None:
    run = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[
            {"node_id": "completed", "action": "generate_text"},
            {"node_id": "pending", "action": "generate_image"},
        ],
    )
    update_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=run["run_id"],
        action_updates=[
            {"node_id": "completed", "action": "generate_text", "status": "completed"}
        ],
    )

    cancelled = reconcile_workflow_runs_with_canvas_nodes(
        project_dir=tmp_path,
        canvas_id="default",
        existing_node_ids={"completed"},
    )

    assert cancelled == [run["run_id"]]
    reconciled = read_workflow_run(
        project_dir=tmp_path, canvas_id="default", run_id=run["run_id"]
    )
    assert reconciled is not None
    assert reconciled["status"] == "cancelled"
    assert reconciled["metadata"]["cancel_reason"] == "workflow_nodes_deleted"

    late_heartbeat = update_workflow_run(
        project_dir=tmp_path,
        canvas_id="default",
        run_id=run["run_id"],
        status="running",
    )
    assert late_heartbeat is not None
    assert late_heartbeat["status"] == "cancelled"


def test_reconcile_keeps_run_when_an_unfinished_node_still_exists(tmp_path: Path) -> None:
    run = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "pending", "action": "generate_image"}],
    )

    cancelled = reconcile_workflow_runs_with_canvas_nodes(
        project_dir=tmp_path,
        canvas_id="default",
        existing_node_ids={"pending"},
    )

    assert cancelled == []
    preserved = read_workflow_run(
        project_dir=tmp_path, canvas_id="default", run_id=run["run_id"]
    )
    assert preserved is not None
    assert preserved["status"] == "running"


def test_stale_running_workflow_is_marked_interrupted(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    run = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "pending", "action": "generate_image"}],
    )
    path = tmp_path / "freezone" / "_workflow_runs" / "default" / f"{run['run_id']}.json"
    payload = read_workflow_run(
        project_dir=tmp_path, canvas_id="default", run_id=run["run_id"]
    )
    assert payload is not None
    payload["updated_at"] = (now - timedelta(seconds=61)).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(payload), encoding="utf-8")

    interrupted = interrupt_stale_workflow_runs(
        project_dir=tmp_path,
        canvas_id="default",
        stale_after_seconds=60,
        now=now,
    )

    assert interrupted == [run["run_id"]]
    recovered = read_workflow_run(
        project_dir=tmp_path, canvas_id="default", run_id=run["run_id"]
    )
    assert recovered is not None
    assert recovered["status"] == "interrupted"
    assert recovered["metadata"]["interrupt_reason"] == "runner_heartbeat_expired"


@pytest.mark.parametrize(
    ("actions", "message"),
    [([], "at least one action"), (["bad"], "must be an object")],
)
def test_workflow_run_rejects_invalid_actions(
    tmp_path: Path, actions: list, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        create_workflow_run(
            project_dir=tmp_path,
            project_id="project-a",
            canvas_id="default",
            actions=actions,
        )


def test_workflow_run_rejects_unknown_action_update(tmp_path: Path) -> None:
    run = create_workflow_run(
        project_dir=tmp_path,
        project_id="project-a",
        canvas_id="default",
        actions=[{"node_id": "one", "action": "generate_image"}],
    )

    with pytest.raises(ValueError, match="workflow action not found"):
        update_workflow_run(
            project_dir=tmp_path,
            canvas_id="default",
            run_id=run["run_id"],
            action_updates=[
                {"node_id": "other", "action": "generate_image", "status": "completed"}
            ],
        )
