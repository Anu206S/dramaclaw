#!/usr/bin/env bash
# Install or verify the DramaClaw-supported Hermes CLI version.
set -euo pipefail

root_dir="$(cd "$(dirname "$0")/.." && pwd)"
version_file="$root_dir/.hermes-version"
mode="${1:-install}"

if [ ! -f "$version_file" ]; then
  echo "Missing $version_file" >&2
  exit 2
fi

required_version="$(tr -d '[:space:]' < "$version_file")"
install_spec="${HERMES_INSTALL_SPEC:-hermes-agent[acp]==${required_version}}"

current_version() {
  if ! command -v hermes >/dev/null 2>&1; then
    return 1
  fi
  hermes --version 2>/dev/null | sed -n 's/^Hermes Agent v\([0-9][0-9.]*\).*/\1/p' | head -n 1
}

current="$(current_version || true)"
if [ "$current" = "$required_version" ]; then
  echo "Hermes $current is installed."
  exit 0
fi

if [ "$mode" = "--check" ] || [ "$mode" = "check" ]; then
  if [ -z "$current" ]; then
    echo "Hermes is not installed. Run: scripts/setup-hermes.sh" >&2
  else
    echo "Hermes $current is installed, but DramaClaw requires $required_version. Run: scripts/setup-hermes.sh" >&2
  fi
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to install Hermes. Install uv first: https://docs.astral.sh/uv/" >&2
  exit 2
fi

echo "Installing Hermes ${required_version} from ${install_spec} ..."
uv tool install "$install_spec" --force

updated="$(current_version || true)"
if [ "$updated" != "$required_version" ]; then
  echo "Hermes install finished, but found version '${updated:-unknown}' instead of '$required_version'." >&2
  exit 1
fi

echo "Hermes $updated is ready."
