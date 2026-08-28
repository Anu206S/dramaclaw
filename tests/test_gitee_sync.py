from __future__ import annotations

import os
import shlex
import subprocess
import textwrap
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/sync-to-gitee.yml"
GITEE_URL = "git@gitee.com:dramaclaw/dramaclaw.git"


def workflow_script(name: str) -> str:
    # Execute the workflow's literal shell block, without a YAML dependency.
    step = WORKFLOW.read_text().split(f"      - name: {name}\n", 1)[1]
    step = step.split("\n      - name:", 1)[0]
    script = step.split("        run: ", 1)[1]
    if script.startswith("|\n"):
        return textwrap.dedent(script[2:])
    return script.strip()


def test_sync_can_reuse_a_checkout_and_replace_a_stale_remote(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    remote = tmp_path / "remote.git"
    checkout.mkdir()
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=checkout, check=True, capture_output=True
    )
    (checkout / "README").write_text("fixture\n")
    subprocess.run(["git", "add", "README"], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Test",
            "-c",
            "user.email=ci-test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=checkout,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "tag", "fixture-v1"], cwd=checkout, check=True)
    env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{remote.as_uri()}.insteadOf",
        "GIT_CONFIG_VALUE_0": GITEE_URL,
        # Any unexpected SSH connection fails instead of reaching the network.
        "GIT_SSH_COMMAND": "false",
    }
    script = workflow_script("Push to Gitee")
    for _ in range(2):
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", script],
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
        )
    subprocess.run(
        ["git", "remote", "set-url", "gitee", "stale.invalid:old.git"],
        cwd=checkout,
        check=True,
    )
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=checkout,
        env=env,
        check=True,
        capture_output=True,
    )
    url = subprocess.check_output(
        ["git", "config", "remote.gitee.url"], cwd=checkout, text=True
    ).strip()
    assert url == GITEE_URL
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
    ).strip()
    for ref in ["refs/heads/main", "refs/tags/fixture-v1"]:
        mirrored = subprocess.check_output(
            ["git", "--git-dir", str(remote), "rev-parse", ref], text=True
        ).strip()
        assert mirrored == head


def test_ssh_uses_task_local_paths_and_cleanup_preserves_home(tmp_path: Path) -> None:
    task_temp = tmp_path / "task temp with spaces"
    task_temp.mkdir()
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    old_key = home / ".ssh/id_ed25519"
    old_key.write_text("existing-home-key\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    keyscan = tools / "ssh-keyscan"
    keyscan.write_text(
        "#!/bin/sh\nprintf 'gitee.com ssh-ed25519 fixture-host-key\\n'\n"
    )
    keyscan.chmod(0o755)
    github_env = task_temp / "github-env"
    env = {
        **os.environ,
        "HOME": str(home),
        "RUNNER_TEMP": str(task_temp),
        "GITHUB_ENV": str(github_env),
        "GITEE_SSH_PRIVATE_KEY": "fixture-only\n",
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
    }
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", workflow_script("Setup task-local SSH key")],
        env=env,
        check=True,
        capture_output=True,
    )
    key = task_temp / "gitee-ssh/key"
    assert key.read_text().strip() == "fixture-only"
    assert key.stat().st_mode & 0o777 == 0o600
    command = github_env.read_text().strip().split("=", 1)[1]
    config = subprocess.check_output(
        shlex.split(command) + ["-G", "git@gitee.com"], env=env, text=True
    )
    assert f"identityfile {key}" in config
    assert str(task_temp / "gitee-ssh/known_hosts") in config
    assert "identitiesonly yes" in config
    subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            workflow_script("Remove task-local SSH credentials"),
        ],
        env=env,
        check=True,
        capture_output=True,
    )
    assert not key.parent.exists()
    assert old_key.read_text() == "existing-home-key\n"
