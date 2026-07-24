from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def workflow_run_client(monkeypatch, tmp_path):
    from novelvideo.api.auth import get_api_user
    from novelvideo.api.routes import freezone

    ctx = SimpleNamespace(
        project_id="proj_demo",
        owner_username="alice",
        project_name="demo",
        output_dir=str(tmp_path),
        state_dir=str(tmp_path),
        runtime_dir=str(tmp_path / "_runtime"),
        is_home_node=True,
    )

    async def fake_resolve(project: str, user: dict, *, required_role: str = "editor"):
        return ctx, "alice", "demo", tmp_path, str(tmp_path)

    monkeypatch.setattr(freezone, "_resolve_freezone_project", fake_resolve)
    app = FastAPI()
    app.include_router(freezone.router, prefix="/api/v1")
    app.dependency_overrides[get_api_user] = lambda: {
        "id": "u-alice",
        "username": "alice",
    }
    return TestClient(app)


def test_workflow_run_api_lifecycle(workflow_run_client: TestClient) -> None:
    base = "/api/v1/projects/proj_demo/freezone/canvases/default/workflow-runs"
    created_response = workflow_run_client.post(
        base,
        json={"actions": [{"node_id": "image-1", "action": "generate_image"}]},
    )
    assert created_response.status_code == 200
    created = created_response.json()["data"]

    patched_response = workflow_run_client.patch(
        f"{base}/{created['run_id']}",
        json={
            "status": "completed",
            "action_updates": [
                {"node_id": "image-1", "action": "generate_image", "status": "completed"}
            ],
        },
    )
    assert patched_response.status_code == 200
    assert patched_response.json()["data"]["status"] == "completed"

    assert workflow_run_client.get(f"{base}/{created['run_id']}").json()["data"][
        "run_id"
    ] == created["run_id"]
    assert workflow_run_client.get(base).json()["data"]["runs"][0]["run_id"] == created[
        "run_id"
    ]


def test_workflow_run_api_rejects_empty_actions(workflow_run_client: TestClient) -> None:
    response = workflow_run_client.post(
        "/api/v1/projects/proj_demo/freezone/canvases/default/workflow-runs",
        json={"actions": []},
    )

    assert response.status_code == 400


def test_workflow_run_list_cancels_orphaned_failed_record(
    workflow_run_client: TestClient,
    monkeypatch,
) -> None:
    from novelvideo.api.routes import freezone

    base = "/api/v1/projects/proj_demo/freezone/canvases/default/workflow-runs"
    created = workflow_run_client.post(
        base,
        json={"actions": [{"node_id": "deleted-node", "action": "generate_image"}]},
    ).json()["data"]
    workflow_run_client.patch(
        f"{base}/{created['run_id']}",
        json={
            "status": "failed",
            "action_updates": [
                {
                    "node_id": "deleted-node",
                    "action": "generate_image",
                    "status": "failed",
                }
            ],
        },
    )
    monkeypatch.setattr(freezone.canvas_store, "read_canvas", lambda *_args, **_kwargs: None)

    runs = workflow_run_client.get(base).json()["data"]["runs"]

    listed = next(item for item in runs if item["run_id"] == created["run_id"])
    assert listed["status"] == "cancelled"
    assert listed["resumable"] is False
    assert listed["metadata"]["cancel_reason"] == "workflow_nodes_deleted"
