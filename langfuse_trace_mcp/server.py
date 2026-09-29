from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from langfuse import Langfuse
from mcp.server.fastmcp import FastMCP

from . import tool_docs as docs
from .uuid_utils import IdCache, short_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_SNAKE_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE2 = re.compile(r"([a-z0-9])([A-Z])")
NOT_FETCHED = "<not fetched>"
MAX_PAGE_SIZE = 1000

# Field groups of the v2 observations API (``core`` is always returned).
FIELDS_LISTING = "core,basic"
FIELDS_METADATA = "core,basic,time,metadata,model,usage,prompt,metrics"
FIELDS_CONTENT = "core,basic,io"

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


def _parse_io(value: Any) -> Any:
    """v2 observations return input/output as raw strings; decode JSON when possible."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _cond(column: str, operator: str, value: Any, type_: str = "string") -> dict:
    return {"type": type_, "column": column, "operator": operator, "value": value}


ROOT_COND = _cond("isRootObservation", "=", True, "boolean")


def _list_observations(
    conditions: list[dict],
    *,
    fields: str = FIELDS_LISTING,
    max_rows: int = MAX_PAGE_SIZE,
) -> tuple[list[Any], bool]:
    """List observations matching ``conditions`` via the v2 observations API.

    Every constraint goes into the ``filter`` JSON: when it is present the API
    ignores the individual query-parameter filters. Walks the cursor until
    ``max_rows`` rows are collected; returns (rows, more_rows_available).
    """
    rows: list[Any] = []
    cursor: str | None = None
    while True:
        resp = _lf().api.observations.get_many(
            filter=json.dumps(conditions),
            fields=fields,
            limit=min(max_rows - len(rows), MAX_PAGE_SIZE),
            cursor=cursor,
        )
        rows.extend(resp.data)
        cursor = resp.meta.cursor
        if not cursor or not resp.data or len(rows) >= max_rows:
            return rows[:max_rows], bool(cursor)


def _trace_observations(trace_id: str) -> list[Any]:
    rows, _ = _list_observations(
        [_cond("traceId", "=", trace_id)], max_rows=100_000
    )
    return rows


def _get_root(trace_id: str, fields: str = FIELDS_LISTING) -> Any:
    """A trace in Langfuse v4 is represented by its root observation."""
    rows, _ = _list_observations(
        [ROOT_COND, _cond("traceId", "=", trace_id)], fields=fields, max_rows=1
    )
    if not rows:
        raise ValueError(f"No root observation found for trace {trace_id!r}.")
    return rows[0]


def _get_observation(trace_id: str, obs_id: str, fields: str) -> Any:
    rows, _ = _list_observations(
        [_cond("traceId", "=", trace_id), _cond("id", "=", obs_id)],
        fields=fields,
        max_rows=1,
    )
    if not rows:
        raise ValueError(f"No span {obs_id!r} found in trace {trace_id!r}.")
    return rows[0]


def _trace_record(root: Any) -> dict:
    """Trace-level fields, taken from the trace's root observation."""
    return {
        "id": root.trace_id,
        "name": root.name,
        "timestamp": root.start_time,
        "environment": root.environment,
        "session_id": root.session_id,
        "user_id": root.user_id,
        "version": root.version,
        "level": root.level,
    }


def _format_trace(
    root: Any,
    fields: list[str] | None = None,
    all_trace_ids: list[str] | None = None,
    strip_unfetched: bool = False,
) -> dict:
    raw = _trace_record(root)

    all_ids = all_trace_ids or []
    raw["id"] = short_id(root.trace_id, all_ids)
    if raw.get("session_id"):
        raw["session_id"] = short_id(raw["session_id"], all_ids)

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


def _resolve_trace(prefix: str) -> str:
    """Resolve a trace id prefix via the cache, falling back to the API.

    Full ids and prefixes that were never cached are looked up against the
    root observations, so no prior get_traces call is required.
    """
    try:
        return _cache.resolve(prefix, "trace")
    except ValueError:
        pass

    rows, _ = _list_observations(
        [ROOT_COND, _cond("traceId", "starts with", prefix.lower())], max_rows=2
    )
    matches = sorted({r.trace_id for r in rows})
    if not matches:
        raise ValueError(f"No trace found matching prefix {prefix!r}.")
    if len(matches) > 1:
        display = [short_id(m, matches) for m in matches]
        raise ValueError(f"Multiple traces match prefix {prefix!r}: {display}")
    _cache.add(matches[0], "trace")
    return matches[0]


def _resolve_span_in_trace(trace_id_prefix: str, span_id_prefix: str) -> tuple[str, str]:
    """Resolve a span prefix scoped to a specific trace's observations.

    This avoids ambiguity when short span prefixes collide across traces.
    Returns (trace_id, span_id).
    """
    trace_id = _resolve_trace(trace_id_prefix)
    all_obs_ids = [o.id for o in _trace_observations(trace_id)]
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
    return trace_id, matches[0]


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
    # Langfuse v4 (events_only) has no traces endpoint: a trace is listed as
    # its root observation, newest first.
    conditions = [ROOT_COND]
    if trace_id_prefix:
        conditions.append(_cond("traceId", "starts with", trace_id_prefix.lower()))
    if name:
        conditions.append(_cond("name", "starts with", name))
    if session_id_prefix:
        conditions.append(_cond("sessionId", "starts with", session_id_prefix))
    if environment:
        conditions.append(_cond("environment", "starts with", environment))
    if version:
        conditions.append(_cond("version", "starts with", version))
    if from_timestamp:
        ts = datetime.fromisoformat(from_timestamp).isoformat()
        conditions.append(_cond("startTime", ">=", ts, "datetime"))
    if to_timestamp:
        ts = datetime.fromisoformat(to_timestamp).isoformat()
        conditions.append(_cond("startTime", "<=", ts, "datetime"))
    if tags:
        conditions.append(_cond("tags", "all of", tags, "arrayOptions"))

    # Cursor pagination only: fetch through the requested page and slice.
    # The extra row tells us whether another page exists.
    skip = (page - 1) * limit
    rows, more = _list_observations(conditions, max_rows=skip + limit + 1)
    collected_traces = rows[skip : skip + limit]
    more_api_pages = more or len(rows) > skip + limit

    all_ids = [t.trace_id for t in collected_traces]
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
    trace_id = _resolve_trace(trace_id_prefix)
    observations = _trace_observations(trace_id)
    if not observations:
        raise ValueError(f"No observations found for trace {trace_id_prefix!r}.")

    all_obs_ids = [o.id for o in observations]
    obs_id_set = set(all_obs_ids)
    # Top-level = parent is None OR parent is not in the observations set
    # (OTEL/LangGraph can nest everything under a span that isn't exported)
    children = sorted(
        (obs for obs in observations if obs.parent_observation_id not in obs_id_set),
        key=lambda o: o.start_time,
    )
    child_ids = [c.id for c in children]
    _cache.add_many(all_obs_ids, "observation")

    return json.dumps(
        {
            "trace_id": short_id(trace_id, []),
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
    trace_id, span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)
    obs = _get_observation(trace_id, span_id, FIELDS_METADATA)

    result = _format_observation(obs, fields)

    return json.dumps(result, indent=2, default=str)


@mcp_server.tool()
def get_span_children(
    trace_id_prefix: str,
    span_id_prefix: str,
) -> str:
    trace_id, span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)

    children, _ = _list_observations(
        [_cond("traceId", "=", trace_id), _cond("parentObservationId", "=", span_id)],
        max_rows=100,
    )
    children.sort(key=lambda o: o.start_time)
    child_ids = [c.id for c in children]
    _cache.add_many(child_ids, "observation")

    return json.dumps(
        {
            "span_id": short_id(span_id, []),
            "children": [
                _observation_summary(c, all_obs_ids=child_ids) for c in children
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

    trace_id = _resolve_trace(trace_id_prefix)
    # The trace's input/output is its root observation's.
    root = _get_root(trace_id, FIELDS_CONTENT)
    value = _parse_io(getattr(root, content_type))

    internal_uuids = _collect_uuids(value)
    if internal_uuids:
        _cache.add_many(internal_uuids, "unknown")
    value = _shorten_uuids(value, internal_uuids)

    result_value, unfetched = _content_result(value, fields)

    out: dict[str, Any] = {
        "id": short_id(trace_id, []),
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

    trace_id, span_id = _resolve_span_in_trace(trace_id_prefix, span_id_prefix)
    obs = _get_observation(trace_id, span_id, FIELDS_CONTENT)
    value = _parse_io(getattr(obs, content_type))

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

    trace_id, pre_id = _resolve_span_in_trace(trace_id_prefix, pre_span_id_prefix)
    _, post_id = _resolve_span_in_trace(trace_id_prefix, post_span_id_prefix)

    if pre_id == post_id and not (pre_field == "input" and post_field == "output"):
        raise ValueError(
            "When comparing the same span, pre_field must be 'input' "
            "and post_field must be 'output'"
        )

    pre_obs = _get_observation(trace_id, pre_id, FIELDS_CONTENT)
    post_obs = _get_observation(trace_id, post_id, FIELDS_CONTENT)

    if (
        pre_id != post_id
        and pre_obs.parent_observation_id != post_obs.parent_observation_id
    ):
        raise ValueError(
            "Spans must be at the same level (same parent). "
            f"Pre span parent: {pre_obs.parent_observation_id}, "
            f"Post span parent: {post_obs.parent_observation_id}"
        )

    pre_value = _parse_io(getattr(pre_obs, pre_field))
    post_value = _parse_io(getattr(post_obs, post_field))

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
