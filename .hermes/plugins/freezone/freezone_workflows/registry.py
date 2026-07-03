"""Load Freezone workflow definitions from per-workflow directories."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any


def registered_workflows() -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    package_name = __package__ or "novelvideo.freezone.workflows"
    package = importlib.import_module(package_name)
    for module_info in pkgutil.iter_modules(package.__path__):
        if (
            not module_info.ispkg
            or module_info.name.startswith("_")
            or module_info.name == "registry"
        ):
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}.workflow")
        workflow = getattr(module, "WORKFLOW", None)
        if isinstance(workflow, dict):
            workflows.append(dict(workflow))
    return sorted(
        workflows,
        key=lambda item: (int(item.get("order") or 999), str(item.get("workflow_type") or "")),
    )


def workflow_by_type() -> dict[str, dict[str, Any]]:
    return {str(item["workflow_type"]): item for item in registered_workflows()}


def workflow_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for workflow in registered_workflows():
        workflow_type = str(workflow["workflow_type"])
        aliases[_normalize_alias(workflow_type)] = workflow_type
        for alias in workflow.get("aliases", []):
            aliases[_normalize_alias(alias)] = workflow_type
    return aliases


def _normalize_alias(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
