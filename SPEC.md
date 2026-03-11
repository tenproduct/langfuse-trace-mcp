# Langfuse Trace MCP Server

* UVX based mcp server
* config: langfuse host, secret key, and public key

Designed around traces, spans (observations)

## Features

### Get traces

Search and list traces, sorted by timestamp (newest first). Input/output not available here — use `get_trace_content`.

Input params:
```
* trace id prefix*
* name prefix
* date/time range
* session id prefix*
* environment (prefix)
* tags
* version (prefix)
* fields (fields to fetch; input/output excluded)
* limit (page size, default 10)
* page (page number, default 1; page 2 with limit 10 returns items 10–19)
```

Unfetched field keys are returned once at the top level (not repeated per trace).

* denotes IDs which use short UUID prefix matching

### Get trace children

List the immediate children spans of a trace (id, name, type, start_time). No trace-level fields returned.

Input params:
```
* trace id prefix*
```

### Get trace content

Get the full input or output of a trace. If the content is a dict, use `fields` to select specific keys; unselected keys are listed in `unfetched` with their byte sizes.

Input params:
```
* trace id prefix*
* content_type ('input' or 'output')
* fields (optional, for dict content)
```

Returns `{ result, unfetched? }`.

### Get span

Get name, all immediate children spans, and requested fields. Input/output not available here — use `get_span_content`.

Input params:
```
* trace id prefix* (scopes span lookup)
* span id prefix*
* fields (fields to fetch; input/output excluded)
```

The keys of fields not fetched will also be returned with a placeholder.

### Get span children

List the immediate children of a span (id, name, type, start_time).

Input params:
```
* trace id prefix* (scopes span lookup)
* span id prefix*
```

### Get span content

Get the full input or output of a span. If the content is a dict, use `fields` to select specific keys; unselected keys are listed in `unfetched` with their byte sizes.

Input params:
```
* trace id prefix* (scopes span lookup)
* span id prefix*
* content_type ('input' or 'output')
* fields (optional, for dict content)
```

Returns `{ result, unfetched? }`.

### Get difference

Get the difference between the input/output of 2 spans that are at the same level

Input params:
```
* trace id prefix* (scopes span lookup)
pre: span id prefix* + "input" or "output"
post: span id prefix* + "input" or "output"
```
span id prefixes can be the same, if so, pre must be input and post must be output.


## UUID handling

IDs are displayed as short UUID prefixes (minimum 8 hex chars, like git short hashes) — just enough to disambiguate within each result set. The server maintains an in-memory cache of all UUIDs it has returned, so subsequent tools can resolve short prefixes without re-scanning the API.

Workflow: use get_traces first to populate the cache, then reference traces/spans by their short prefixes in get_trace_children, get_trace_content, get_span, get_span_children, get_span_content, and get_difference.

