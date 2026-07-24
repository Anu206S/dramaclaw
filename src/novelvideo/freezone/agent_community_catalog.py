"""Read and install Freezone community Skill Bundles from a trusted catalog."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen

from novelvideo.freezone.agent_bundle_store import install_agent_bundle, validate_agent_bundle

COMMUNITY_CATALOG_URL = "https://raw.githubusercontent.com/dramaclaw/dramaclaw-skills/main/catalog.json"
COMMUNITY_RAW_HOST = "raw.githubusercontent.com"
COMMUNITY_RAW_PATH_PREFIX = "/dramaclaw/dramaclaw-skills/"
COMMUNITY_BUNDLE_PATH_FRAGMENT = "/skills/"


def list_community_catalog(*, username: str) -> dict[str, Any]:
    catalog = _fetch_json(COMMUNITY_CATALOG_URL)
    _validate_catalog(catalog)
    return catalog


def install_community_bundle(*, username: str, bundle_url: str) -> dict[str, Any]:
    trusted_url = _validate_trusted_bundle_url(bundle_url)
    bundle = _fetch_json(trusted_url)
    validate_agent_bundle(bundle, username=username)
    return install_agent_bundle(username=username, payload=bundle)


def _validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != "dramaclaw.community-catalog.v1":
        raise ValueError("invalid community catalog schema_version")
    items = catalog.get("items")
    if not isinstance(items, list):
        raise ValueError("invalid community catalog items")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid community catalog item")
        bundle_url = item.get("bundle_url")
        if not isinstance(bundle_url, str):
            raise ValueError("community catalog item missing bundle_url")
        _validate_trusted_bundle_url(bundle_url)


def _validate_trusted_bundle_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != COMMUNITY_RAW_HOST:
        raise ValueError("untrusted community Bundle URL")
    if not parsed.path.startswith(COMMUNITY_RAW_PATH_PREFIX):
        raise ValueError("untrusted community Bundle URL")
    if COMMUNITY_BUNDLE_PATH_FRAGMENT not in parsed.path or not parsed.path.endswith("/bundle.json"):
        raise ValueError("untrusted community Bundle URL")
    return url


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(2_000_000)
        payload = json.loads(data.decode("utf-8"))
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to fetch community catalog data") from exc
    if not isinstance(payload, dict):
        raise ValueError("community response must be a JSON object")
    return payload
