"""CLI entry point — mirrors every MCP tool as a subcommand."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import server as srv
from . import tool_docs as docs
from .uuid_utils import CACHE_FILENAME


def _init_client() -> None:
    """Initialise the Langfuse client from env vars (same as the MCP entry point)."""
    import os

    from langfuse import Langfuse

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
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    srv._langfuse = Langfuse(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_get_traces(args: argparse.Namespace) -> None:
    print(
        srv.get_traces(
            trace_id_prefix=args.trace_id_prefix,
            name=args.name,
            from_timestamp=args.from_timestamp,
            to_timestamp=args.to_timestamp,
            session_id_prefix=args.session_id_prefix,
            environment=args.environment,
            tags=args.tags,
            version=args.version,
            fields=_resolve_fields(args),
            limit=args.limit,
            page=args.page,
        )
    )


def _cmd_get_trace_children(args: argparse.Namespace) -> None:
    print(srv.get_trace_children(trace_id_prefix=args.trace_id_prefix))


def _cmd_get_trace_content(args: argparse.Namespace) -> None:
    print(
        srv.get_trace_content(
            trace_id_prefix=args.trace_id_prefix,
            content_type=args.content_type,
            fields=_resolve_fields(args),
        )
    )


def _cmd_get_span(args: argparse.Namespace) -> None:
    print(
        srv.get_span(
            trace_id_prefix=args.trace_id_prefix,
            span_id_prefix=args.span_id_prefix,
            fields=_resolve_fields(args),
        )
    )


def _cmd_get_span_children(args: argparse.Namespace) -> None:
    print(
        srv.get_span_children(
            trace_id_prefix=args.trace_id_prefix,
            span_id_prefix=args.span_id_prefix,
        )
    )


def _cmd_get_span_content(args: argparse.Namespace) -> None:
    print(
        srv.get_span_content(
            trace_id_prefix=args.trace_id_prefix,
            span_id_prefix=args.span_id_prefix,
            content_type=args.content_type,
            fields=_resolve_fields(args),
        )
    )


def _cmd_get_difference(args: argparse.Namespace) -> None:
    print(
        srv.get_difference(
            trace_id_prefix=args.trace_id_prefix,
            pre_span_id_prefix=args.pre_span_id_prefix,
            pre_field=args.pre_field,
            post_span_id_prefix=args.post_span_id_prefix,
            post_field=args.post_field,
        )
    )


# ---------------------------------------------------------------------------
# Shared argument helpers
# ---------------------------------------------------------------------------


def _add_trace_id(parser: argparse.ArgumentParser, doc: docs.ToolDoc) -> None:
    parser.add_argument(
        "trace_id_prefix",
        help=doc.params["trace_id_prefix"].description,
    )


def _add_span_id(parser: argparse.ArgumentParser, doc: docs.ToolDoc) -> None:
    parser.add_argument(
        "span_id_prefix",
        help=doc.params["span_id_prefix"].description,
    )


def _add_content_type(parser: argparse.ArgumentParser, doc: docs.ToolDoc) -> None:
    parser.add_argument(
        "content_type",
        choices=["input", "output"],
        help=doc.params["content_type"].description,
    )


def _add_metadata_fields(
    parser: argparse.ArgumentParser,
    doc: docs.ToolDoc,
    default: list[str] | None = None,
) -> None:
    parser.add_argument(
        "--fields",
        nargs="*",
        default=default,
        help=doc.params["fields"].description,
    )
    parser.add_argument(
        "--all-fields",
        action="store_true",
        default=False,
        help="Include all metadata fields (overrides --fields).",
    )


def _add_content_fields(parser: argparse.ArgumentParser, doc: docs.ToolDoc) -> None:
    parser.add_argument(
        "--fields",
        nargs="*",
        default=None,
        help=doc.params["fields"].description,
    )
    parser.add_argument(
        "--all-fields",
        action="store_true",
        default=False,
        help="Return all content fields (overrides --fields).",
    )


def _resolve_fields(args: argparse.Namespace) -> list[str] | None:
    """Return None if --all-fields was passed, otherwise args.fields."""
    if args.all_fields:
        return None
    return args.fields


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="langfuse-trace-cli",
        description=(
            "CLI for exploring Langfuse traces and spans.\n\n"
            "IDs are short UUID prefixes (min 8 hex chars). The cache is persisted to\n"
            ".langfuse-trace-cache.json so prefixes work across invocations. Full UUIDs\n"
            "(with dashes) are also accepted directly.\n\n"
            "Requires env vars: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get-traces
    d = docs.GET_TRACES
    p = sub.add_parser(
        "get-traces",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--trace-id-prefix",
        dest="trace_id_prefix",
        default=None,
        help=d.params["trace_id_prefix"].description,
    )
    p.add_argument("--name", default=None, help=d.params["name"].description)
    p.add_argument(
        "--from-timestamp",
        dest="from_timestamp",
        default=None,
        help=d.params["from_timestamp"].description,
    )
    p.add_argument(
        "--to-timestamp",
        dest="to_timestamp",
        default=None,
        help=d.params["to_timestamp"].description,
    )
    p.add_argument(
        "--session-id-prefix",
        dest="session_id_prefix",
        default=None,
        help=d.params["session_id_prefix"].description,
    )
    p.add_argument(
        "--environment",
        default=None,
        help=d.params["environment"].description,
    )
    p.add_argument(
        "--tags",
        nargs="*",
        default=None,
        help=d.params["tags"].description,
    )
    p.add_argument(
        "--version",
        default=None,
        help=d.params["version"].description,
    )
    _add_metadata_fields(p, d, default=["name"])
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help=d.params["limit"].description,
    )
    p.add_argument(
        "--page",
        type=int,
        default=1,
        help=d.params["page"].description,
    )
    p.set_defaults(func=_cmd_get_traces)

    # get-trace-children
    d = docs.GET_TRACE_CHILDREN
    p = sub.add_parser(
        "get-trace-children",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    p.set_defaults(func=_cmd_get_trace_children)

    # get-trace-content
    d = docs.GET_TRACE_CONTENT
    p = sub.add_parser(
        "get-trace-content",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    _add_content_type(p, d)
    _add_content_fields(p, d)
    p.set_defaults(func=_cmd_get_trace_content)

    # get-span
    d = docs.GET_SPAN
    p = sub.add_parser(
        "get-span",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    _add_span_id(p, d)
    _add_metadata_fields(p, d, default=["name"])
    p.set_defaults(func=_cmd_get_span)

    # get-span-children
    d = docs.GET_SPAN_CHILDREN
    p = sub.add_parser(
        "get-span-children",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    _add_span_id(p, d)
    p.set_defaults(func=_cmd_get_span_children)

    # get-span-content
    d = docs.GET_SPAN_CONTENT
    p = sub.add_parser(
        "get-span-content",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    _add_span_id(p, d)
    _add_content_type(p, d)
    _add_content_fields(p, d)
    p.set_defaults(func=_cmd_get_span_content)

    # get-difference
    d = docs.GET_DIFFERENCE
    p = sub.add_parser(
        "get-difference",
        help=d.summary,
        description=f"{d.summary}\n\n{d.body}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_trace_id(p, d)
    p.add_argument(
        "pre_span_id_prefix",
        help=d.params["pre_span_id_prefix"].description,
    )
    p.add_argument(
        "pre_field",
        choices=["input", "output"],
        help=d.params["pre_field"].description,
    )
    p.add_argument(
        "post_span_id_prefix",
        help=d.params["post_span_id_prefix"].description,
    )
    p.add_argument(
        "post_field",
        choices=["input", "output"],
        help=d.params["post_field"].description,
    )
    p.set_defaults(func=_cmd_get_difference)

    return parser


def cli_main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _init_client()

    cache_path = Path.cwd() / CACHE_FILENAME
    srv._cache.load(cache_path)

    try:
        args.func(args)
    finally:
        srv._cache.save(cache_path)
