"""CLI entry point — mirrors every MCP tool as a subcommand."""

from __future__ import annotations

import argparse
import sys

from . import server as srv


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
            fields=args.fields,
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
            fields=args.fields,
        )
    )


def _cmd_get_span(args: argparse.Namespace) -> None:
    print(
        srv.get_span(
            trace_id_prefix=args.trace_id_prefix,
            span_id_prefix=args.span_id_prefix,
            fields=args.fields,
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
            fields=args.fields,
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


def _add_trace_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("trace_id_prefix", help="Short hex prefix of the trace.")


def _add_span_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("span_id_prefix", help="Short hex prefix of the span.")


def _add_content_type(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "content_type", choices=["input", "output"], help="'input' or 'output'."
    )


def _add_metadata_fields(
    parser: argparse.ArgumentParser, default: list[str] | None = None
) -> None:
    parser.add_argument(
        "--fields",
        nargs="*",
        default=default,
        help="Metadata fields to include (default: %(default)s). Omit value for all.",
    )


def _add_content_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fields",
        nargs="*",
        default=[],
        help="Dict keys to return values for (default: none — sizes only). Omit value for all.",
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="langfuse-trace-cli",
        description="CLI for exploring Langfuse traces and spans.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get-traces
    p = sub.add_parser("get-traces", help="Search and list traces.")
    p.add_argument("--trace-id-prefix", dest="trace_id_prefix", default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--from-timestamp", dest="from_timestamp", default=None)
    p.add_argument("--to-timestamp", dest="to_timestamp", default=None)
    p.add_argument("--session-id-prefix", dest="session_id_prefix", default=None)
    p.add_argument("--environment", default=None)
    p.add_argument("--tags", nargs="*", default=None)
    p.add_argument("--version", default=None)
    _add_metadata_fields(p, default=["name"])
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--page", type=int, default=1)
    p.set_defaults(func=_cmd_get_traces)

    # get-trace-children
    p = sub.add_parser(
        "get-trace-children", help="List immediate child spans of a trace."
    )
    _add_trace_id(p)
    p.set_defaults(func=_cmd_get_trace_children)

    # get-trace-content
    p = sub.add_parser("get-trace-content", help="Get input/output payload of a trace.")
    _add_trace_id(p)
    _add_content_type(p)
    _add_content_fields(p)
    p.set_defaults(func=_cmd_get_trace_content)

    # get-span
    p = sub.add_parser("get-span", help="Get a span's metadata.")
    _add_trace_id(p)
    _add_span_id(p)
    _add_metadata_fields(p, default=["name"])
    p.set_defaults(func=_cmd_get_span)

    # get-span-children
    p = sub.add_parser("get-span-children", help="List immediate children of a span.")
    _add_trace_id(p)
    _add_span_id(p)
    p.set_defaults(func=_cmd_get_span_children)

    # get-span-content
    p = sub.add_parser("get-span-content", help="Get input/output payload of a span.")
    _add_trace_id(p)
    _add_span_id(p)
    _add_content_type(p)
    _add_content_fields(p)
    p.set_defaults(func=_cmd_get_span_content)

    # get-difference
    p = sub.add_parser(
        "get-difference", help="Structured diff between two sibling spans."
    )
    _add_trace_id(p)
    p.add_argument("pre_span_id_prefix", help="Short hex prefix for the 'before' span.")
    p.add_argument(
        "pre_field",
        choices=["input", "output"],
        help="'input' or 'output' from the pre span.",
    )
    p.add_argument("post_span_id_prefix", help="Short hex prefix for the 'after' span.")
    p.add_argument(
        "post_field",
        choices=["input", "output"],
        help="'input' or 'output' from the post span.",
    )
    p.set_defaults(func=_cmd_get_difference)

    return parser


def cli_main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _init_client()
    args.func(args)
