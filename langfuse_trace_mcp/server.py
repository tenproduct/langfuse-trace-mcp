from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from langfuse import Langfuse
from mcp.server.fastmcp import FastMCP

from . import tool_docs as docs
from .uuid_utils import IdCache, matches_prefix, short_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_SNAKE_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE2 = re.compile(r"([a-z0-9])([A-Z])")
NOT_FETCHED = "<not fetched>"
MAX_SEARCH_PAGES = 10

# ---------------------------------------------------------------------------
# Server & state
# ---------------------------------------------------------------------------

mcp_server = FastMCP(
    "langfuse-trace-mcp",
    instructions="""\
Explore Langfuse traces and spans to understand LLM pipeline behaviour.

Before using these tools, you MUST search for and read LANGFUSE.md in the project root. \
If it exists, follow its guidance on how traces map to the codebase and how to debug them.

When investigating spans, try and match span names to functions, graph nodes, tools, \
or agents in the codebase to understand the input/output schemata. This tells \
you which fields are meaningful to compare or retrieve.

Use the 'fields' parameter on every tool that has one to keep responses small. \
Prefer get_difference over get_span_content when comparing data across spans.
IDs are short UUID prefixes (like git short hashes); span tools require the \
parent trace prefix to scope lookups.\

Traces can be paginated with 'page' and 'limit', but for large result sets it's more efficient to \
filter by trace_id_prefix, name, session_id_prefix, environment, or version to narrow down results. \
There is no "offset" parameter, but you can use page to skip results. \
""",
)
_langfuse: Langfuse | None = None
_cache = IdCache()


def _lf() -> Langfuse:
    if _langfuse is None:
        raise RuntimeError("Langfuse client not initialized")
    return _langfuse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snake(name: str) -> str:
    return _SNAKE_RE2.sub(r"\1_\2", _SNAKE_RE1.sub(r"\1_\2", name)).lower()


def _normalize(d: dict) -> dict:
    return {_snake(k): v for k, v in d.items()}


def _shorten_uuids(value: Any, all_uuids: list[str]) -> Any:
    """Recursively shorten UUID strings found in values."""
    if isinstance(value, str):
        return UUID_RE.sub(lambda m: short_id(m.group(), all_uuids), value)
    if isinstance(value, dict):
        return {k: _shorten_uuids(v, all_uuids) for k, v in value.items()}
    if isinstance(value, list):
        return [_shorten_uuids(v, all_uuids) for v in value]
    return value


def _collect_uuids(value: Any) -> list[str]:
    """Collect all UUID strings found in a value."""
    if isinstance(value, str):
        return UUID_RE.findall(value)
    if isinstance(value, dict):
        result = []
        for v in value.values():
            result.extend(_collect_uuids(v))
        return result
    if isinstance(value, list):
        result = []
        for v in value:
            result.extend(_collect_uuids(v))
        return result
    return []


BLOCKED_CONTENT_FIELDS = {"input", "output"}


def _filter_fields(data: dict, fields: list[str] | None) -> dict:
    """Show values for requested fields, NOT_FETCHED for others. ID always included.

    input/output are always excluded — use get_span_content / get_trace_content."""
    if fields is None:
        return {
            k: v if k not in BLOCKED_CONTENT_FIELDS else NOT_FETCHED
            for k, v in data.items()
        }
    always = {"id"}
    requested = set(fields) - BLOCKED_CONTENT_FIELDS
    return {
        k: v if (k in always or k in requested) else NOT_FETCHED
        for k, v in data.items()
    }


def _value_size(value: Any) -> int:
    """Approximate byte size of a value via JSON serialisation."""
    try:
        return len(json.dumps(value, default=str).encode())
    except Exception:
        return len(str(value).encode())


def _content_result(
    value: Any, fields: list[str] | None
) -> tuple[Any, dict[str, int] | None]:
    """Split content into (result, unfetched).

    If value is a dict and fields is given, result contains only the
    requested keys; unfetched maps remaining keys to their byte sizes.
    Otherwise result is the full value and unfetched is None.
    """
    if fields is not None and isinstance(value, dict):
        result = {k: v for k, v in value.items() if k in fields}
        unfetched = {k: _value_size(v) for k, v in value.items() if k not in fields}
        return result, unfetched if unfetched else None
    return value, None


def _format_trace(
    trace: Any,
    fields: list[str] | None = None,
    all_trace_ids: list[str] | None = None,
    strip_unfetched: bool = False,
) -> dict:
    raw = _normalize(trace.model_dump())

    all_ids = all_trace_ids or []
    raw["id"] = short_id(trace.id, all_ids)
    if raw.get("session_id"):
        raw["session_id"] = short_id(raw["session_id"], all_ids)

    raw.pop("observations", None)
    raw.pop("scores", None)

    filtered = _filter_fields(raw, fields)
    if strip_unfetched:
        filtered = {k: v for k, v in filtered.items() if v is not NOT_FETCHED}
    return filtered


def _format_observation(
    obs: Any,
    fields: list[str] | None = None,
    all_obs_ids: list[str] | None = None,
) -> dict:
    raw = _normalize(obs.model_dump())

    all_ids = all_obs_ids or []
    raw["id"] = short_id(obs.id, all_ids)
    if raw.get("trace_id"):
        raw["trace_id"] = short_id(raw["trace_id"], all_ids)
    if raw.get("parent_observation_id"):
        raw["parent_observation_id"] = short_id(raw["parent_observation_id"], all_ids)

    return _filter_fields(raw, fields)


def _observation_summary(obs: Any, all_obs_ids: list[str] | None = None) -> dict:
    """Minimal summary for child-observation listings."""
    all_ids = all_obs_ids or []
    return {
        "id": short_id(obs.id, all_ids),
        "name": obs.name,
        "type": obs.type,
        "start_time": str(obs.start_time) if obs.start_time else None,
    }


def _resolve_cached(prefix: str, entity: str) -> str:
    """Resolve a prefix using the cache. Falls back to API for exact UUID."""
    try:
        return _cache.resolve(prefix, entity)
    except ValueError:
        pass

    # If the prefix looks like a full UUID, try a direct API fetch
    lf = _lf()
    if len(prefix) >= 32:
        try:
            if entity == "trace":
                return lf.api.trace.get(prefix).id
            else:
                return lf.api.legacy.observations_v1.get(prefix).id
        except Exception:
            pass

    raise ValueError(
        f"No {entity} found matching prefix {prefix!r}. "
        "Use get_traces or get_trace_children first to load IDs into the cache."
    )


def _resolve_span_in_trace(trace_id_prefix: str, span_id_prefix: str) -> str:
    """Resolve a span prefix scoped to a specific trace's observations.

    This avoids ambiguity when short span prefixes collide across traces.
    """
    trace_id = _resolve_cached(trace_id_prefix, "trace")
    trace = _lf().api.trace.get(trace_id)

    all_obs_ids = [o.id for o in trace.observations]
    _cache.add_many(all_obs_ids, "observation")

    prefix_lower = span_id_prefix.lower()
    matches = [oid for oid in all_obs_ids if oid.lower().startswith(prefix_lower)]

    if not matches:
        raise ValueError(
            f"No span matching prefix {span_id_prefix!r} in trace {trace_id_prefix!r}."
        )
    if len(matches) > 1:
        display = [short_id(m, matches) for m in matches]
        raise ValueError(
            f"Multiple spans match prefix {span_id_prefix!r} in trace "
            f"{trace_id_prefix!r}: {display}"
        )
    return matches[0]


def _compute_diff(pre: Any, post: Any) -> dict:
    """Structured diff: {added, deleted, modified}. Recursive for nested dicts."""
    if isinstance(pre, dict) and isinstance(post, dict):
        added = {k: v for k, v in post.items() if k not in pre}
        deleted = {k: v for k, v in pre.items() if k not in post}
        modified: dict[str, Any] = {}
        for k in pre:
            if k in post and pre[k] != post[k]:
                if isinstance(pre[k], dict) and isinstance(post[k], dict):
                    sub = _compute_diff(pre[k], post[k])
                    if sub:
                        modified[k] = sub
                else:
                    modified[k] = {"pre": pre[k], "post": post[k]}
        result: dict[str, Any] = {}
        if added:
            result["added"] = added
        if deleted:
            result["deleted"] = deleted
        if modified:
            result["modified"] = modified
        return result
    else:
        return {"pre": pre, "post": post}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp_server.tool()
def get_traces(
    trace_id_prefix: str | None = None,
    name: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    session_id_prefix: str | None = None,
    environment: str | None = None,
    tags: list[str] | None = None,
    version: str | None = None,
    fields: list[str] | None = ["name"],
    limit: int = 10,
    page: int = 1,
) -> str:
    lf = _lf()

    api_kwargs: dict[str, Any] = {"order_by": "timestamp.desc"}
    if from_timestamp:
        api_kwargs["from_timestamp"] = datetime.fromisoformat(from_timestamp)
    if to_timestamp:
        api_kwargs["to_timestamp"] = datetime.fromisoformat(to_timestamp)
    if tags:
        api_kwargs["tags"] = tags

    has_client_filters = any(
        [
            trace_id_prefix,
            name,
            session_id_prefix,
            environment,
            version,
        ]
    )

    if not has_client_filters:
        # No client-side filtering — pass page/limit straight to the API.
        resp = lf.api.trace.list(page=page, limit=limit, **api_kwargs)
        collected_traces = list(resp.data)
        more_api_pages = resp.meta.page < resp.meta.total_pages
    else:
        # Client-side filtering: scan from API page 1, skip first
        # (page-1)*limit matches, then collect up to limit matches.
        skip = (page - 1) * limit
        skipped = 0
        collected_traces = []
        api_page = 1
        more_api_pages = True

        while (
            len(collected_traces) < limit
            and api_page <= MAX_SEARCH_PAGES
            and more_api_pages
        ):
            resp = lf.api.trace.list(page=api_page, limit=100, **api_kwargs)

            for t in resp.data:
                if trace_id_prefix and not matches_prefix(t.id, trace_id_prefix):
                    continue
                if name and (not t.name or not t.name.startswith(name)):
                    continue
                if session_id_prefix and (
                    not t.session_id
                    or not matches_prefix(t.session_id, session_id_prefix)
                ):
                    continue
                if environment and (
                    not t.environment or not t.environment.startswith(environment)
                ):
                    continue
                if version and (not t.version or not t.version.startswith(version)):
                    continue

                if skipped < skip:
                    skipped += 1
                    continue

                collected_traces.append(t)
                if len(collected_traces) >= limit:
                    break

            more_api_pages = resp.meta.page < resp.meta.total_pages
            api_page += 1

    all_ids = [t.id for t in collected_traces]
    _cache.add_many(all_ids, "trace")

    # Build compact traces (no per-row placeholders) + single top-level unfetched list
    results = [
        _format_trace(t, fields, all_trace_ids=all_ids, strip_unfetched=True)
        for t in collected_traces
    ]

    # Compute unfetched keys once from the first trace (all share the same schema)
    unfetched_keys: list[str] = []
    if collected_traces and fields is not None:
        sample = _format_trace(collected_traces[0], fields, all_trace_ids=all_ids)
        unfetched_keys = sorted(k for k, v in sample.items() if v is NOT_FETCHED)

    out: dict[str, Any] = {
        "traces": results,
        "has_more": more_api_pages,
    }
    if unfetched_keys:
        out["unfetched_keys"] = unfetched_keys

    return json.dumps(out, indent=2, default=str)


@mcp_server.tool()
def get_trace_children(
    trace_id_prefix: str,
) -> str:
    trace_id = _resolve_cached(trace_id_prefix, "trace")
    trace = _lf().api.trace.get(trace_id)

    all_obs_ids = [o.id for o in trace.observations]
    obs_id_set = set(all_obs_ids)
    # Top-level = parent is None OR parent is not in the observations set
    # (OTEL/LangGraph nests everything under a root span that isn't an observation)
    children = [obs for obs in trace.observations if obs.parent_observation_id not in obs_id_set]
    child_ids = [c.id for c in children]
    _cache.add_many(all_obs_ids, "observation")

    return json.dumps(
        {
            "trace_id": short_id(trace.id, []),
            "children": [
                _observation_summary(c, all_obs_ids=child_ids) for c in children
            ],
        },
        indent=2,
        default=str,
    )


@mcp_server.tool()
def get_span(
    trace_id_prefix: str,
    span_id_prefix: str,
    fields: list[str] | None = ["name"],
) -> str:
    span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)
    obs = _lf().api.legacy.observations_v1.get(span_id)

    result = _format_observation(obs, fields)

    return json.dumps(result, indent=2, default=str)


@mcp_server.tool()
def get_span_children(
    trace_id_prefix: str,
    span_id_prefix: str,
) -> str:
    span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)

    children_resp = _lf().api.legacy.observations_v1.get_many(parent_observation_id=span_id, limit=100)
    child_ids = [c.id for c in children_resp.data]
    _cache.add_many(child_ids, "observation")

    return json.dumps(
        {
            "span_id": short_id(span_id, []),
            "children": [
                _observation_summary(c, all_obs_ids=child_ids)
                for c in children_resp.data
            ],
        },
        indent=2,
        default=str,
    )


@mcp_server.tool()
def get_trace_content(
    trace_id_prefix: str,
    content_type: str,
    fields: list[str] | None = None,
) -> str:
    if content_type not in ("input", "output"):
        raise ValueError(
            f"content_type must be 'input' or 'output', got {content_type!r}"
        )

    trace_id = _resolve_cached(trace_id_prefix, "trace")
    trace = _lf().api.trace.get(trace_id)
    value = getattr(trace, content_type)

    internal_uuids = _collect_uuids(value)
    if internal_uuids:
        _cache.add_many(internal_uuids, "unknown")
    value = _shorten_uuids(value, internal_uuids)

    result_value, unfetched = _content_result(value, fields)

    out: dict[str, Any] = {
        "id": short_id(trace.id, []),
        "content_type": content_type,
        "result": result_value,
    }
    if unfetched is not None:
        out["unfetched"] = unfetched

    return json.dumps(out, indent=2, default=str)


@mcp_server.tool()
def get_span_content(
    trace_id_prefix: str,
    span_id_prefix: str,
    content_type: str,
    fields: list[str] | None = None,
) -> str:
    if content_type not in ("input", "output"):
        raise ValueError(
            f"content_type must be 'input' or 'output', got {content_type!r}"
        )

    span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)
    obs = _lf().api.legacy.observations_v1.get(span_id)
    value = getattr(obs, content_type)

    internal_uuids = _collect_uuids(value)
    if internal_uuids:
        _cache.add_many(internal_uuids, "unknown")
    value = _shorten_uuids(value, internal_uuids)

    result_value, unfetched = _content_result(value, fields)

    out: dict[str, Any] = {
        "id": short_id(obs.id, []),
        "name": obs.name,
        "content_type": content_type,
        "result": result_value,
    }
    if unfetched is not None:
        out["unfetched"] = unfetched

    return json.dumps(out, indent=2, default=str)


@mcp_server.tool()
def get_difference(
    trace_id_prefix: str,
    pre_span_id_prefix: str,
    pre_field: str,
    post_span_id_prefix: str,
    post_field: str,
) -> str:
    if pre_field not in ("input", "output"):
        raise ValueError(f"pre_field must be 'input' or 'output', got {pre_field!r}")
    if post_field not in ("input", "output"):
        raise ValueError(f"post_field must be 'input' or 'output', got {post_field!r}")

    pre_id = _resolve_span_in_trace(trace_id_prefix, pre_span_id_prefix)
    post_id = _resolve_span_in_trace(trace_id_prefix, post_span_id_prefix)

    if pre_id == post_id and not (pre_field == "input" and post_field == "output"):
        raise ValueError(
            "When comparing the same span, pre_field must be 'input' "
            "and post_field must be 'output'"
        )

    lf = _lf()
    pre_obs = lf.api.legacy.observations_v1.get(pre_id)
    post_obs = lf.api.legacy.observations_v1.get(post_id)

    if (
        pre_id != post_id
        and pre_obs.parent_observation_id != post_obs.parent_observation_id
    ):
        raise ValueError(
            "Spans must be at the same level (same parent). "
            f"Pre span parent: {pre_obs.parent_observation_id}, "
            f"Post span parent: {post_obs.parent_observation_id}"
        )

    pre_value = getattr(pre_obs, pre_field)
    post_value = getattr(post_obs, post_field)

    diff = _compute_diff(pre_value, post_value)

    return json.dumps(diff, indent=2, default=str)


# ---------------------------------------------------------------------------
# Assign generated docstrings
# ---------------------------------------------------------------------------

get_traces.__doc__ = docs.GET_TRACES.mcp_docstring()
get_trace_children.__doc__ = docs.GET_TRACE_CHILDREN.mcp_docstring()
get_trace_content.__doc__ = docs.GET_TRACE_CONTENT.mcp_docstring()
get_span.__doc__ = docs.GET_SPAN.mcp_docstring()
get_span_children.__doc__ = docs.GET_SPAN_CHILDREN.mcp_docstring()
get_span_content.__doc__ = docs.GET_SPAN_CONTENT.mcp_docstring()
get_difference.__doc__ = docs.GET_DIFFERENCE.mcp_docstring()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import os

    host = os.environ.get("LANGFUSE_HOST")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")

    if not all([host, public_key, secret_key]):
        missing = [
            name
            for name, val in [
                ("LANGFUSE_HOST", host),
                ("LANGFUSE_PUBLIC_KEY", public_key),
                ("LANGFUSE_SECRET_KEY", secret_key),
            ]
            if not val
        ]
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    global _langfuse
    _langfuse = Langfuse(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
    )

    mcp_server.run(transport="stdio")
