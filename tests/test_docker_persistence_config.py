from __future__ import annotations

import re
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).parents[1]
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.release.yml",
    "docker-compose.selfhosted.yml",
    "docker-compose.selfhosted.release.yml",
)


def test_all_compose_variants_persist_generated_media_in_ce_data_volume() -> None:
    for relative_path in COMPOSE_FILES:
        compose = yaml.safe_load((REPOSITORY_ROOT / relative_path).read_text())
        api = compose["services"]["api"]

        assert api["environment"] | {
            "NOVELVIDEO_DATA_ROOT": "/data",
            "NOVELVIDEO_OUTPUT_DIR": "/data/output",
            "NOVELVIDEO_STATE_DIR": "/data/state",
            "NOVELVIDEO_RUNTIME_DIR": "/data/runtime",
        } == api["environment"]
        assert "ce-data:/data" in api["volumes"]


def test_env_example_configures_data_root_instead_of_individual_directories() -> None:
    env_example = (REPOSITORY_ROOT / ".env.example").read_text()

    assert re.search(r"^NOVELVIDEO_OUTPUT_DIR=", env_example, re.MULTILINE) is None
    assert "# NOVELVIDEO_DATA_ROOT=" in env_example


def test_all_ce_published_ports_are_loopback_only_without_changing_container_ports() -> None:
    for relative_path in COMPOSE_FILES:
        compose = yaml.safe_load((REPOSITORY_ROOT / relative_path).read_text())
        for name, service in compose["services"].items():
            for port in service.get("ports", []):
                assert port.startswith("127.0.0.1:"), (relative_path, name, port)
        assert compose["services"]["api"]["ports"][0].endswith(":8780")
        assert compose["services"]["web"]["environment"]["BACKEND_HOST"] == "api"


def test_docker_api_keeps_listening_on_container_interface() -> None:
    assert "--host 0.0.0.0" in (REPOSITORY_ROOT / "Dockerfile").read_text()
