"""Query construction, response parsing and threshold evaluation (no I/O)."""

from __future__ import annotations

import enum
import fnmatch
from dataclasses import dataclass
from typing import Any

USED_PCT = "system.filesystem.used.pct"
TOTAL = "system.filesystem.total"
AVAILABLE = "system.filesystem.available"
MOUNT = "system.filesystem.mount_point"
HOST = "host.name"


class Status(enum.IntEnum):
    """Nagios-compatible status codes, usable directly as process exit codes."""

    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


@dataclass(frozen=True)
class Thresholds:
    warning: float = 80.0
    critical: float = 90.0

    def __post_init__(self) -> None:
        if not 0 < self.warning < self.critical <= 100:
            raise ValueError("thresholds must satisfy 0 < warning < critical <= 100")

    def evaluate(self, used_percent: float) -> Status:
        if used_percent >= self.critical:
            return Status.CRITICAL
        if used_percent >= self.warning:
            return Status.WARNING
        return Status.OK


@dataclass(frozen=True)
class FilesystemUsage:
    host: str
    mount: str
    used_percent: float
    total_bytes: int
    available_bytes: int
    status: Status

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "mount": self.mount,
            "used_percent": self.used_percent,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "status": self.status.name,
        }


def build_query(since: str = "15m", host_filter: str | None = None, max_hosts: int = 1000) -> dict[str, Any]:
    """Aggregation returning the most recent sample per host and mount point."""
    filters: list[dict[str, Any]] = [
        {"range": {"@timestamp": {"gte": f"now-{since}"}}},
        {"exists": {"field": USED_PCT}},
    ]
    if host_filter:
        filters.append({"wildcard": {HOST: {"value": host_filter}}})
    return {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "hosts": {
                "terms": {"field": HOST, "size": max_hosts},
                "aggs": {
                    "mounts": {
                        "terms": {"field": MOUNT, "size": 200},
                        "aggs": {
                            "latest": {
                                "top_metrics": {
                                    "metrics": [{"field": USED_PCT}, {"field": TOTAL}, {"field": AVAILABLE}],
                                    "sort": {"@timestamp": "desc"},
                                }
                            }
                        },
                    }
                },
            }
        },
    }


def parse_response(
    response: dict[str, Any],
    thresholds: Thresholds,
    exclude_mounts: list[str] | None = None,
) -> list[FilesystemUsage]:
    """Turn the aggregation response into evaluated results, worst first."""
    patterns = exclude_mounts or []
    results: list[FilesystemUsage] = []
    for host_bucket in response.get("aggregations", {}).get("hosts", {}).get("buckets", []):
        host = str(host_bucket["key"])
        for mount_bucket in host_bucket.get("mounts", {}).get("buckets", []):
            mount = str(mount_bucket["key"])
            if any(fnmatch.fnmatch(mount, p) for p in patterns):
                continue
            top = mount_bucket.get("latest", {}).get("top", [])
            if not top:
                continue
            metrics = top[0].get("metrics", {})
            ratio = metrics.get(USED_PCT)
            if ratio is None:
                continue
            used = round(float(ratio) * 100, 1)
            results.append(
                FilesystemUsage(
                    host=host,
                    mount=mount,
                    used_percent=used,
                    total_bytes=int(metrics.get(TOTAL) or 0),
                    available_bytes=int(metrics.get(AVAILABLE) or 0),
                    status=thresholds.evaluate(used),
                )
            )
    return sorted(results, key=lambda r: (-r.status, -r.used_percent, r.host, r.mount))


def overall_status(results: list[FilesystemUsage]) -> Status:
    if not results:
        return Status.UNKNOWN
    return max(r.status for r in results)


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} PiB"  # pragma: no cover
