"""Seed a live Elasticsearch with Metricbeat-shaped file system documents for integration testing.

Creates an index with the same field types Metricbeat uses (keyword host and mount fields, float usage
ratio), writes an older and a newer sample per file system, and refreshes the index. fsmon must report
the newer sample, which proves the "latest value" aggregation works against a real cluster.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
INDEX = "metricbeat-ci"
GIB = 1024**3

MAPPINGS = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "host": {"properties": {"name": {"type": "keyword"}}},
            "system": {
                "properties": {
                    "filesystem": {
                        "properties": {
                            "mount_point": {"type": "keyword"},
                            "used": {"properties": {"pct": {"type": "float"}}},
                            "total": {"type": "long"},
                            "available": {"type": "long"},
                        }
                    }
                }
            },
        }
    }
}

# host, mount, older ratio, newer ratio, size in GiB
SAMPLES = [
    ("web01", "/", 0.95, 0.41, 50),  # was critical, now healthy: proves the newest sample wins
    ("web01", "/var", 0.70, 0.84, 100),  # warning
    ("db01", "/", 0.30, 0.35, 50),
    ("db01", "/var/lib/pgsql", 0.90, 0.93, 500),  # critical
]


def doc(host: str, mount: str, ratio: float, size_gib: int, ts: datetime) -> dict[str, object]:
    total = size_gib * GIB
    return {
        "@timestamp": ts.isoformat(),
        "host": {"name": host},
        "system": {
            "filesystem": {
                "mount_point": mount,
                "used": {"pct": ratio},
                "total": total,
                "available": int(total * (1 - ratio)),
            }
        },
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    with httpx.Client(base_url=ES_URL, timeout=30) as es:
        es.delete(f"/{INDEX}")
        es.put(f"/{INDEX}", json=MAPPINGS).raise_for_status()
        lines: list[str] = []
        for host, mount, older, newer, size in SAMPLES:
            for ratio, age in ((older, 10), (newer, 1)):
                lines.append(json.dumps({"index": {"_index": INDEX}}))
                lines.append(json.dumps(doc(host, mount, ratio, size, now - timedelta(minutes=age))))
        response = es.post(
            "/_bulk?refresh=true",
            content="\n".join(lines) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        response.raise_for_status()
        if response.json().get("errors"):
            print(response.text, file=sys.stderr)
            return 1
    print(f"seeded {len(SAMPLES) * 2} documents into {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
