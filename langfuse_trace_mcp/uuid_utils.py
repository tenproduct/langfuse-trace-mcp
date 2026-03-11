from __future__ import annotations


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

        Raises ValueError if zero or multiple matches.
        """
        prefix_lower = prefix.lower()
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


def matches_prefix(uuid_str: str, prefix: str | None) -> bool:
    """Check if a UUID starts with the given prefix string."""
    if prefix is None:
        return True
    return uuid_str.lower().startswith(prefix.lower())
