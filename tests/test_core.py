from __future__ import annotations

from typing import Any

import pytest

from fsmon.core import Status, Thresholds, build_query, human_bytes, overall_status, parse_response


def test_thresholds_evaluate_boundaries() -> None:
    t = Thresholds(80, 90)
    assert t.evaluate(79.9) is Status.OK
    assert t.evaluate(80.0) is Status.WARNING
    assert t.evaluate(90.0) is Status.CRITICAL


@pytest.mark.parametrize(("warning", "critical"), [(90, 80), (0, 50), (80, 101), (80, 80)])
def test_invalid_thresholds_rejected(warning: float, critical: float) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        Thresholds(warning, critical)


def test_query_selects_latest_sample_per_host_and_mount() -> None:
    q = build_query("30m")
    filters = q["query"]["bool"]["filter"]
    assert {"range": {"@timestamp": {"gte": "now-30m"}}} in filters
    latest = q["aggs"]["hosts"]["aggs"]["mounts"]["aggs"]["latest"]["top_metrics"]
    assert latest["sort"] == {"@timestamp": "desc"}
    assert {"field": "system.filesystem.used.pct"} in latest["metrics"]
    assert q["size"] == 0


def test_query_host_filter() -> None:
    q = build_query(host_filter="web*")
    assert {"wildcard": {"host.name": {"value": "web*"}}} in q["query"]["bool"]["filter"]


def test_parse_sorts_worst_first_and_converts_percent(mixed_response: dict[str, Any]) -> None:
    results = parse_response(mixed_response, Thresholds(80, 90))
    assert [(r.host, r.mount, r.status) for r in results[:3]] == [
        ("db01", "/snap/core", Status.CRITICAL),
        ("db01", "/var/lib/pgsql", Status.CRITICAL),
        ("web01", "/var", Status.WARNING),
    ]
    pgsql = next(r for r in results if r.mount == "/var/lib/pgsql")
    assert pgsql.used_percent == 93.5
    assert pgsql.total_bytes == 500 * 1024**3


def test_parse_excludes_mounts_by_glob(mixed_response: dict[str, Any]) -> None:
    results = parse_response(mixed_response, Thresholds(), exclude_mounts=["/snap/*"])
    assert all(not r.mount.startswith("/snap") for r in results)
    assert len(results) == 4


def test_parse_handles_empty_and_incomplete_buckets() -> None:
    response = {
        "aggregations": {
            "hosts": {
                "buckets": [
                    {"key": "h1", "mounts": {"buckets": [{"key": "/", "latest": {"top": []}}]}},
                    {
                        "key": "h2",
                        "mounts": {"buckets": [{"key": "/", "latest": {"top": [{"metrics": {}}]}}]},
                    },
                ]
            }
        }
    }
    assert parse_response(response, Thresholds()) == []
    assert parse_response({}, Thresholds()) == []


def test_overall_status() -> None:
    assert overall_status([]) is Status.UNKNOWN


@pytest.mark.parametrize(
    ("value", "expected"),
    [(512, "512 B"), (2048, "2.0 KiB"), (5 * 1024**3, "5.0 GiB"), (3 * 1024**4, "3.0 TiB")],
)
def test_human_bytes(value: int, expected: str) -> None:
    assert human_bytes(value) == expected
