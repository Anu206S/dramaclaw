#!/usr/bin/env python3
"""Read-only validation for a local DramaClaw Agent Kit installation."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


REQUIRED = (
    "pyproject.toml",
    "src/novelvideo/chat/dramaclaw_mcp.py",
    "src/novelvideo/chat/workflow_mcp.py",
    ".hermes/plugins/dramaclaw/__init__.py",
    ".hermes/plugins/freezone/__init__.py",
)


def _ce_source_requirement() -> dict[str, object]:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    requirement = manifest.get("requires", {}).get("dramaclaw_ce")
    if not isinstance(requirement, dict):
        raise SystemExit("Agent Kit manifest has no verifiable DramaClaw CE requirement")
    return requirement


def _checkout_contains_revision(ce_root: Path, revision: str) -> bool:
    if not revision or not (ce_root / ".git").exists():
        return False
    completed = subprocess.run(
        ["git", "-C", str(ce_root), "merge-base", "--is-ancestor", revision, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ce-dir", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8780")
    parser.add_argument("--skip-api", action="store_true")
    args = parser.parse_args()

    ce_root = Path(args.ce_dir).expanduser().resolve()
    requirement = _ce_source_requirement()
    required_files = requirement.get("required_files")
    if not isinstance(required_files, list) or not all(
        isinstance(name, str) and name for name in required_files
    ):
        raise SystemExit("Agent Kit manifest has invalid DramaClaw CE required_files")
    missing = [
        name
        for name in dict.fromkeys((*REQUIRED, *required_files))
        if not (ce_root / name).is_file()
    ]
    python_candidates = (
        ce_root / ".venv" / "bin" / "python",
        ce_root / ".venv" / "Scripts" / "python.exe",
    )
    if not any(path.is_file() for path in python_candidates):
        missing.append(".venv Python (run uv sync)")
    kit_root = Path(__file__).resolve().parents[1]
    if not (kit_root / "skills" / "dramaclaw-workflows" / "SKILL.md").is_file():
        missing.append("agent-kit/skills/dramaclaw-workflows/SKILL.md")
    if missing:
        raise SystemExit("Missing required files:\n- " + "\n- ".join(missing))
    revision = str(requirement.get("contains_commit") or "").strip()
    if not _checkout_contains_revision(ce_root, revision):
        raise SystemExit(
            "DramaClaw CE checkout does not contain the Agent Kit compatibility "
            f"revision: {revision or 'missing'}"
        )

    health: dict[str, object] = {"checked": False}
    if not args.skip_api:
        try:
            with urllib.request.urlopen(
                args.api_url.rstrip("/") + "/healthz", timeout=3
            ) as response:
                health = {
                    "checked": True,
                    "status": response.status,
                    "ok": response.status == 200,
                }
        except (OSError, urllib.error.URLError) as exc:
            raise SystemExit(f"DramaClaw API health check failed: {exc}") from exc
    print(
        json.dumps(
            {"ok": True, "ce_dir": str(ce_root), "api": health},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
