"""Shared tool documentation — single source of truth for MCP docstrings and CLI help."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    description: str


@dataclass(frozen=True)
class ToolDoc:
    summary: str
    body: str = ""
    params: dict[str, Param] = field(default_factory=dict)

    def mcp_docstring(self) -> str:
        """Build a Google-style docstring for the MCP tool decorator."""
        parts = [self.summary]
        parts.append("")
        parts.append("You MUST search for and read LANGFUSE.md if you haven't already.")
        if self.body:
            parts.append("")
            parts.append(self.body)
        if self.params:
            parts.append("")
            parts.append("Args:")
            for name, param in self.params.items():
                parts.append(f"    {name}: {param.description}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Shared param definitions (reused across tools)
# ---------------------------------------------------------------------------

TRACE_ID_PREFIX = Param("Short UUID prefix identifying the trace.")
TRACE_ID_PREFIX_SCOPE = Param(
    "Short UUID prefix of the parent trace (scopes span lookup)."
)
SPAN_ID_PREFIX = Param("Short UUID prefix identifying the span.")
SPAN_ID_PREFIX_PARENT = Param("Short UUID prefix identifying the parent span.")
CONTENT_TYPE = Param("'input' or 'output' — which content to retrieve.")
METADATA_FIELDS = Param(
    "Field names to include values for (input/output excluded — use "
    "get_span_content or get_trace_content). Defaults to ['name']. "
    "Pass None for all."
)
CONTENT_FIELDS = Param(
    "Dict keys to return values for. Defaults to [] (sizes only). None for all."
)

# ---------------------------------------------------------------------------
# Tool docs
# ---------------------------------------------------------------------------

GET_TRACES = ToolDoc(
    summary="Search and list Langfuse traces with optional filtering.",
    body=(
        "Results are sorted by timestamp (newest first). Use 'page' for offset\n"
        "pagination.\n"
        "\n"
        "CONTEXT BUDGET: Use the 'fields' parameter to limit returned data to\n"
        "only what you need (defaults to ['name']). To compare data across spans,\n"
        "prefer get_difference over fetching full content with get_span_content.\n"
        "\n"
        "Workflow: find traces here → drill into one with get_trace_children →\n"
        "inspect spans with get_span → compare with get_difference."
    ),
    params={
        "trace_id_prefix": Param("Filter by trace ID prefix (short hex prefix)."),
        "name": Param("Filter by trace name prefix."),
        "from_timestamp": Param("Start of time range (ISO 8601)."),
        "to_timestamp": Param("End of time range (ISO 8601)."),
        "session_id_prefix": Param("Filter by session ID prefix (short hex prefix)."),
        "environment": Param("Filter by environment prefix."),
        "tags": Param("Filter by exact tags."),
        "version": Param("Filter by version prefix."),
        "fields": METADATA_FIELDS,
        "limit": Param("Maximum number of traces to return (default 10)."),
        "page": Param("Page number for offset pagination (default 1)."),
    },
)

GET_TRACE_CHILDREN = ToolDoc(
    summary="List the immediate children spans of a trace.",
    body=(
        "Returns only children (id, name, type, start_time) — no trace-level\n"
        "fields. Use get_trace_content for trace input/output, get_span for\n"
        "span details, or get_difference to compare spans."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX,
    },
)

GET_TRACE_CONTENT = ToolDoc(
    summary="Get the full input or output content of a trace.",
    body=(
        "NOTE: Prefer get_difference when comparing data across spans — it returns\n"
        "only changes and is much lighter on context.\n"
        "\n"
        "If the content is a dict, use 'fields' to select specific keys. Defaults\n"
        "to [] (no values — only unfetched key sizes). Pass None for all fields."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX,
        "content_type": CONTENT_TYPE,
        "fields": CONTENT_FIELDS,
    },
)

GET_SPAN = ToolDoc(
    summary="Get a single span's metadata with selected fields.",
    body=(
        "Returns span metadata with only selected field values — unselected\n"
        "fields show '<not fetched>'. Does NOT include children — use\n"
        "get_span_children for that.\n"
        "\n"
        "CONTEXT BUDGET: Defaults to ['name'] only. Use 'fields' to request\n"
        "additional metadata (input/output excluded — use get_span_content).\n"
        "To compare data across spans, prefer get_difference over fetching\n"
        "full content with get_span_content."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX_SCOPE,
        "span_id_prefix": SPAN_ID_PREFIX,
        "fields": METADATA_FIELDS,
    },
)

GET_SPAN_CHILDREN = ToolDoc(
    summary="List the immediate children of a span.",
    body=(
        "Returns a list of children with their id, name, type, and start_time.\n"
        "Use this to navigate the span tree without fetching full span metadata."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX_SCOPE,
        "span_id_prefix": SPAN_ID_PREFIX_PARENT,
    },
)

GET_SPAN_CONTENT = ToolDoc(
    summary="Get the full input or output content of a span.",
    body=(
        "NOTE: Prefer get_difference when comparing data across spans — it returns\n"
        "only changes and is much lighter on context.\n"
        "\n"
        "If the content is a dict, use 'fields' to select specific keys. Defaults\n"
        "to [] (no values — only unfetched key sizes). Pass None for all fields."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX_SCOPE,
        "span_id_prefix": SPAN_ID_PREFIX,
        "content_type": CONTENT_TYPE,
        "fields": CONTENT_FIELDS,
    },
)

GET_DIFFERENCE = ToolDoc(
    summary="Get the structural difference between input/output of two sibling spans.",
    body=(
        "PREFERRED over get_span_content when comparing data across spans — returns\n"
        "only changes, keeping context small.\n"
        "\n"
        "Returns a JSON with 'added', 'deleted', and 'modified' keys showing\n"
        "only the changes. Recursive for nested dicts.\n"
        "\n"
        "Both spans must share the same parent. If comparing the same span, pre_field\n"
        "must be 'input' and post_field must be 'output'."
    ),
    params={
        "trace_id_prefix": TRACE_ID_PREFIX_SCOPE,
        "pre_span_id_prefix": Param("Short UUID prefix for the 'before' span."),
        "pre_field": Param(
            "'input' or 'output' — which field to use from the pre span."
        ),
        "post_span_id_prefix": Param("Short UUID prefix for the 'after' span."),
        "post_field": Param(
            "'input' or 'output' — which field to use from the post span."
        ),
    },
)
