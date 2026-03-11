# Langfuse Trace MCP Server

An MCP server for exploring Langfuse traces and spans. IDs are shown as short UUID prefixes (like git short hashes) and cached server-side for fast resolution.

## Tools

- **get_traces** — Search traces with filters (name, tags, environment, version, date range, session/trace ID prefix) and pagination
- **get_trace_children** — List immediate child spans of a trace (id, name, type, start_time)
- **get_trace_content** — Get the full input or output payload of a trace, with optional field selection
- **get_span** — Get a single span/observation with its children and selected fields (requires trace ID prefix)
- **get_span_children** — List immediate child spans of a span (requires trace ID prefix)
- **get_span_content** — Get the full input or output payload of a span, with optional field selection (requires trace ID prefix)
- **get_difference** — Structured diff (added/deleted/modified) between input/output of two sibling spans (requires trace ID prefix)

## Setup

Add to your MCP client config (e.g. VS Code `settings.json`, Claude Desktop `claude_desktop_config.json`).

**From a Git repo (SSH — works with private repos if SSH keys are configured):**
```json
{
  "mcpServers": {
    "langfuse-trace": {
      "command": "uvx",
      "args": ["--from", "git+ssh://git@github.com/user/langfuse_trace_mcp", "langfuse-trace-mcp"],
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