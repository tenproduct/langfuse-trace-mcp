# Langfuse Trace MCP Server

A UVX-based MCP server (stdio transport) for exploring Langfuse traces and spans. Config via environment variables: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

IDs are shown as short UUID prefixes (minimum 8 hex chars, like git short hashes) and cached server-side for fast resolution. UUIDs embedded within content values are also detected, shortened, and added to the cache automatically.

The server instructs the agent to look for a `LANGFUSE.md` file in the project root for codebase-specific trace guidance.

## Tools

### get_traces

Search and list traces, sorted by timestamp (newest first). Input/output content is never included — use `get_trace_content`.

Prefix filters (`trace_id_prefix`, `name`, `session_id_prefix`, `environment`, `version`) are applied client-side; `tags`, `from_timestamp`, `to_timestamp` are passed to the API. Client-side filtering scans up to 10 API pages of 100 results each.

| Parameter           | Type                | Default    | Description                                                     |
| ------------------- | ------------------- | ---------- | --------------------------------------------------------------- |
| `trace_id_prefix`   | `str \| null`       | `null`     | Short hex prefix to filter trace IDs.                           |
| `name`              | `str \| null`       | `null`     | Trace name prefix filter.                                       |
| `from_timestamp`    | `str \| null`       | `null`     | Start of time range (ISO 8601).                                 |
| `to_timestamp`      | `str \| null`       | `null`     | End of time range (ISO 8601).                                   |
| `session_id_prefix` | `str \| null`       | `null`     | Short hex prefix to filter session IDs.                         |
| `environment`       | `str \| null`       | `null`     | Environment prefix filter.                                      |
| `tags`              | `list[str] \| null` | `null`     | Exact tag match.                                                |
| `version`           | `str \| null`       | `null`     | Version prefix filter.                                          |
| `fields`            | `list[str] \| null` | `["name"]` | Metadata fields to include. `null` = all (except input/output). |
| `limit`             | `int`               | `10`       | Page size.                                                      |
| `page`              | `int`               | `1`        | Page number (1-indexed).                                        |

```json
{
  "traces": [{ "id": "<short_hex>", "<field>": "<value>" }],
  "has_more": true,
  "unfetched_keys": ["environment", "version"]
}
```

### get_trace_children

List the immediate child spans of a trace.

| Parameter         | Type  | Default      | Description                             |
| ----------------- | ----- | ------------ | --------------------------------------- |
| `trace_id_prefix` | `str` | *(required)* | Short hex prefix identifying the trace. |

```json
{
  "trace_id": "<short_hex>",
  "children": [{ "id": "<short_hex>", "name": "span-name", "type": "SPAN|GENERATION|EVENT", "start_time": "..." }]
}
```

### get_trace_content

Get the full input or output payload of a trace, with optional field selection for dict content. UUIDs in content are automatically shortened and cached.

| Parameter         | Type                | Default      | Description                                           |
| ----------------- | ------------------- | ------------ | ----------------------------------------------------- |
| `trace_id_prefix` | `str`               | *(required)* | Short hex prefix identifying the trace.               |
| `content_type`    | `str`               | *(required)* | `"input"` or `"output"`.                              |
| `fields`          | `list[str] \| null` | `[]`         | Dict keys to return. `[]` = sizes only. `null` = all. |

```json
{
  "id": "<short_hex>",
  "content_type": "input",
  "result": { "<key>": "<value>" },
  "unfetched": { "<key>": 1234 }
}
```

### get_span

Get a single span's metadata with selected fields. Does not return children or input/output.

| Parameter         | Type                | Default      | Description                                                     |
| ----------------- | ------------------- | ------------ | --------------------------------------------------------------- |
| `trace_id_prefix` | `str`               | *(required)* | Short hex prefix of the parent trace.                           |
| `span_id_prefix`  | `str`               | *(required)* | Short hex prefix of the span.                                   |
| `fields`          | `list[str] \| null` | `["name"]`   | Metadata fields to include. `null` = all (except input/output). |

```json
{
  "id": "<short_hex>",
  "trace_id": "<short_hex>",
  "parent_observation_id": "<short_hex>",
  "name": "span-name",
  "<unfetched_field>": "<not fetched>"
}
```

### get_span_children

List the immediate children of a span.

| Parameter         | Type  | Default      | Description                           |
| ----------------- | ----- | ------------ | ------------------------------------- |
| `trace_id_prefix` | `str` | *(required)* | Short hex prefix of the parent trace. |
| `span_id_prefix`  | `str` | *(required)* | Short hex prefix of the parent span.  |

```json
{
  "span_id": "<short_hex>",
  "children": [{ "id": "<short_hex>", "name": "child-span-name", "type": "SPAN|GENERATION|EVENT", "start_time": "..." }]
}
```

### get_span_content

Get the full input or output payload of a span, with optional field selection for dict content. UUIDs in content are automatically shortened and cached.

| Parameter         | Type                | Default      | Description                                           |
| ----------------- | ------------------- | ------------ | ----------------------------------------------------- |
| `trace_id_prefix` | `str`               | *(required)* | Short hex prefix of the parent trace.                 |
| `span_id_prefix`  | `str`               | *(required)* | Short hex prefix of the span.                         |
| `content_type`    | `str`               | *(required)* | `"input"` or `"output"`.                              |
| `fields`          | `list[str] \| null` | `[]`         | Dict keys to return. `[]` = sizes only. `null` = all. |

```json
{
  "id": "<short_hex>",
  "name": "span-name",
  "content_type": "input",
  "result": { "<key>": "<value>" },
  "unfetched": { "<key>": 1234 }
}
```

### get_difference

Structured diff between input/output of two sibling spans (same parent). Returns only changes. If both span prefixes resolve to the same span, `pre_field` must be `"input"` and `post_field` must be `"output"`.

| Parameter             | Type  | Default      | Description                                 |
| --------------------- | ----- | ------------ | ------------------------------------------- |
| `trace_id_prefix`     | `str` | *(required)* | Short hex prefix of the parent trace.       |
| `pre_span_id_prefix`  | `str` | *(required)* | Short hex prefix for the "before" span.     |
| `pre_field`           | `str` | *(required)* | `"input"` or `"output"` from the pre span.  |
| `post_span_id_prefix` | `str` | *(required)* | Short hex prefix for the "after" span.      |
| `post_field`          | `str` | *(required)* | `"input"` or `"output"` from the post span. |

Dict content:
```json
{ "added": { "<key>": "<new_value>" }, "deleted": { "<key>": "<old_value>" }, "modified": { "<key>": { "pre": "<old>", "post": "<new>" } } }
```

Non-dict content:
```json
{ "pre": "<old_value>", "post": "<new_value>" }
```

## UUID Handling

IDs are displayed as short UUID prefixes (minimum 8 hex chars) — just enough to disambiguate within each result set. The MCP server maintains an in-memory cache; the CLI persists the cache to `.langfuse-trace-cache.json` in the working directory so short prefixes survive across invocations. Full UUIDs (with dashes) are always accepted directly, bypassing the cache.

Workflow: use `get_traces` first to populate the cache, then reference traces/spans by their short prefixes in all other tools.

## CLI

All tools are also available as CLI subcommands via `langfuse-trace-cli`. Requires the same env vars.

Add it as a dev dependency in your project's `pyproject.toml`:

```toml
[tool.uv.sources]
langfuse-trace-mcp = { git = "ssh://git@github.com/tenproduct/langfuse-trace-mcp.git" }

[dependency-groups]
dev = [
    "langfuse-trace-mcp",
]
```

Then `uv sync` and the `langfuse-trace-cli` command is available in your project's virtualenv. In a terminal session with the correct env vars:

```bash
uv run langfuse-trace-cli get-traces --limit 5
```

Use `--all-fields` on the relevant tools to return all fields (equivalent to passing `None` via MCP).

```
langfuse-trace-cli get-traces [--trace-id-prefix X] [--name X] [--from-timestamp X] [--to-timestamp X] [--session-id-prefix X] [--environment X] [--tags T ...] [--version X] [--fields F ...] [--all-fields] [--limit N] [--page N]
langfuse-trace-cli get-trace-children <trace_id_prefix>
langfuse-trace-cli get-trace-content <trace_id_prefix> <input|output> [--fields F ...] [--all-fields]
langfuse-trace-cli get-span <trace_id_prefix> <span_id_prefix> [--fields F ...] [--all-fields]
langfuse-trace-cli get-span-children <trace_id_prefix> <span_id_prefix>
langfuse-trace-cli get-span-content <trace_id_prefix> <span_id_prefix> <input|output> [--fields F ...] [--all-fields]
langfuse-trace-cli get-difference <trace_id_prefix> <pre_span_id_prefix> <input|output> <post_span_id_prefix> <input|output>
```

Output is the same JSON as the corresponding MCP tool.

## Setup

Add to your MCP client config (e.g. VS Code `settings.json`, Claude Desktop `claude_desktop_config.json`).

**From a Git repo (SSH — works with private repos if SSH keys are configured):**
```json
{
  "mcpServers": {
    "langfuse-trace": {
      "command": "uvx",
      "args": ["--from", "git+ssh://git@github.com/tenproduct/langfuse-trace-mcp", "langfuse-trace-mcp"],
      "env": {
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "pk-...",
        "LANGFUSE_SECRET_KEY": "sk-..."
      }
    }
  }
}
```

**From a local clone:**
```json
{
  "mcpServers": {
    "langfuse-trace": {
      "command": "uvx",
      "args": ["--from", "/path/to/langfuse_trace_mcp", "langfuse-trace-mcp"],
      "env": {
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "pk-...",
        "LANGFUSE_SECRET_KEY": "sk-..."
      }
    }
  }
}
```