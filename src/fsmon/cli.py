"""Command-line interface.

Exit codes follow the Nagios plugin convention so fsmon can be used from cron, CI pipelines,
Nagios/Icinga/Zabbix agents or any scheduler: 0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from fsmon import __version__
from fsmon.client import ElasticsearchError, SearchClient
from fsmon.core import (
    FilesystemUsage,
    Status,
    Thresholds,
    build_query,
    human_bytes,
    overall_status,
    parse_response,
)


def format_table(results: list[FilesystemUsage]) -> str:
    headers = ("STATUS", "HOST", "MOUNT", "USED", "AVAILABLE", "SIZE")
    rows = [
        (
            r.status.name,
            r.host,
            r.mount,
            f"{r.used_percent:.1f}%",
            human_bytes(r.available_bytes),
            human_bytes(r.total_bytes),
        )
        for r in results
    ]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in rows]
    return "\n".join(line.rstrip() for line in lines)


def format_nagios(results: list[FilesystemUsage], status: Status) -> str:
    problems = [r for r in results if r.status != Status.OK]
    if status == Status.UNKNOWN:
        summary = "no file system data found in the selected time range"
    elif problems:
        summary = ", ".join(f"{r.host}:{r.mount} {r.used_percent:.1f}%" for r in problems[:10])
    else:
        summary = f"{len(results)} file systems within thresholds"
    perfdata = " ".join(f"'{r.host}:{r.mount}'={r.used_percent:.1f}%" for r in results[:50])
    return f"FSMON {status.name} - {summary} | {perfdata}".rstrip(" |")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="fsmon", description="File system capacity check from Metricbeat data.")
    p.add_argument(
        "--url", default=os.environ.get("ES_URL", "http://localhost:9200"), help="Elasticsearch URL"
    )
    p.add_argument("--index", default="metricbeat-*", help="index pattern holding Metricbeat data")
    p.add_argument("--since", default="15m", help="look-back window, e.g. 15m or 1h (default: 15m)")
    p.add_argument("--host", help="only hosts matching this wildcard pattern")
    p.add_argument("--warning", type=float, default=80.0, help="warning threshold in percent")
    p.add_argument("--critical", type=float, default=90.0, help="critical threshold in percent")
    p.add_argument(
        "--exclude-mount",
        action="append",
        default=[],
        metavar="PATTERN",
        help="mount points to ignore (glob, repeatable), e.g. '/snap/*'",
    )
    p.add_argument("--format", choices=["table", "json", "nagios"], default="table")
    p.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    p.add_argument("--ca-cert", help="CA bundle for TLS verification")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None, client: SearchClient | None = None) -> int:
    args = parse_args(argv)
    try:
        thresholds = Thresholds(args.warning, args.critical)
    except ValueError as exc:
        print(f"fsmon: {exc}", file=sys.stderr)
        return Status.UNKNOWN

    verify: bool | str = False if args.insecure else (args.ca_cert or True)
    owns_client = client is None
    if client is None:
        client = SearchClient(
            args.url,
            api_key=os.environ.get("ES_API_KEY"),
            username=os.environ.get("ES_USERNAME"),
            password=os.environ.get("ES_PASSWORD"),
            verify=verify,
        )
    try:
        response = client.search(args.index, build_query(args.since, args.host))
    except ElasticsearchError as exc:
        if args.format == "nagios":
            print(f"FSMON UNKNOWN - {exc}")
        else:
            print(f"fsmon: {exc}", file=sys.stderr)
        return Status.UNKNOWN
    finally:
        if owns_client:
            client.close()

    results = parse_response(response, thresholds, args.exclude_mount)
    status = overall_status(results)

    if args.format == "json":
        print(json.dumps({"status": status.name, "results": [r.to_dict() for r in results]}, indent=2))
    elif args.format == "nagios":
        print(format_nagios(results, status))
    elif results:
        print(format_table(results))
    else:
        print("No file system data found in the selected time range.")
    return int(status)


if __name__ == "__main__":
    raise SystemExit(main())
