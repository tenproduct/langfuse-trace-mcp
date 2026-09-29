from __future__ import annotations

import json
import os
import re
from pathlib import Path

_FULL_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def cache_path(host: str) -> Path:
    """Per-user, per-host cache file (never the working directory).

    ``LANGFUSE_TRACE_CACHE`` overrides the location; otherwise
    ``$XDG_CACHE_HOME/langfuse-trace-mcp/<host>.json`` (default ``~/.cache``).
    Keying by host keeps prefixes from one Langfuse instance resolving on another.
    """
    override = os.environ.get("LANGFUSE_TRACE_CACHE")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    safe_host = re.sub(r"[^A-Za-z0-9.-]+", "_", host).strip("_") or "default"
    return Path(base) / "langfuse-trace-mcp" / f"{safe_host}.json"


class IdCache:
    """In-memory cache of UUIDs returned to the client, enabling prefix resolution."""

    def __init__(self):
        self._ids: dict[str, str] = {}  # full_uuid -> entity_type

    def add(self, uuid_str: str, entity: str = "unknown") -> None:
        self._ids[uuid_str.lower()] = entity

    def add_many(self, uuids: list[str], entity: str = "unknown") -> None:
        for u in uuids:
            self._ids[u.lower()] = entity

    def resolve(self, prefix: str, entity: str | None = None) -> str:
        """Resolve a prefix to exactly one cached UUID.

        Full UUIDs (with dashes) are accepted directly without cache lookup.
        Raises ValueError if zero or multiple matches.
        """
        prefix_lower = prefix.lower()

        # Full UUID passthrough — skip cache lookup
        if _FULL_UUID_RE.match(prefix_lower):
            return prefix_lower

        matches = [
            uid
            for uid, etype in self._ids.items()
            if uid.startswith(prefix_lower) and (entity is None or etype == entity)
        ]
        if not matches:
            raise ValueError(
                f"No cached {entity or 'id'} found matching prefix {prefix!r}"
            )
        if len(matches) > 1:
            display = [short_id(m, matches) for m in matches]
            raise ValueError(
                f"Multiple {entity or 'id'}s match prefix {prefix!r}: {display}"
            )
        return matches[0]

    # -- Persistence (for CLI use) ------------------------------------------

    def save(self, path: Path) -> None:
        """Write the cache to a JSON file. Raises OSError if unwritable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._ids, indent=2) + "\n")

    def load(self, path: Path) -> None:
        """Merge entries from a JSON file into this cache."""
        try:
            if not path.is_file():
                return
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            for uid, etype in data.items():
                self._ids.setdefault(uid.lower(), etype)


def short_id(uuid_str: str, all_uuids: list[str]) -> str:
    """Return the shortest UUID prefix that uniquely identifies uuid_str among all_uuids.

    Minimum 8 characters (like git short hashes).
    """
    uuid_lower = uuid_str.lower()
    others = [u.lower() for u in all_uuids if u.lower() != uuid_lower]
    if not others:
        return uuid_lower[:8]
    for n in range(8, len(uuid_lower) + 1):
        prefix = uuid_lower[:n]
        if not any(o.startswith(prefix) for o in others):
            return prefix
    return uuid_lower

