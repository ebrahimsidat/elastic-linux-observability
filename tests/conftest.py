from __future__ import annotations

from typing import Any

import pytest

GIB = 1024**3


def mount(name: str, used: float, total_gib: int = 100) -> dict[str, Any]:
    total = total_gib * GIB
    return {
        "key": name,
        "doc_count": 30,
        "latest": {
            "top": [
                {
                    "sort": ["2026-10-25T07:00:00.000Z"],
                    "metrics": {
                        "system.filesystem.used.pct": used,
                        "system.filesystem.total": total,
                        "system.filesystem.available": int(total * (1 - used)),
                    },
                }
            ]
        },
    }


def es_response(hosts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "took": 3,
        "timed_out": False,
        "hits": {"total": {"value": 120, "relation": "eq"}, "hits": []},
        "aggregations": {
            "hosts": {
                "buckets": [{"key": h, "doc_count": 90, "mounts": {"buckets": m}} for h, m in hosts.items()]
            }
        },
    }


@pytest.fixture
def mixed_response() -> dict[str, Any]:
    return es_response(
        {
            "web01": [mount("/", 0.42), mount("/var", 0.83)],
            "db01": [mount("/", 0.51), mount("/var/lib/pgsql", 0.935, 500), mount("/snap/core", 1.0, 1)],
        }
    )
