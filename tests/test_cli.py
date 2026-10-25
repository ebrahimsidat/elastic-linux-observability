from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from conftest import es_response, mount
from fsmon.cli import main
from fsmon.client import SearchClient


def client_returning(
    payload: dict[str, Any], status: int = 200, seen: list[httpx.Request] | None = None
) -> SearchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return SearchClient(
        "http://es.example.test:9200", api_key="secret", transport=httpx.MockTransport(handler)
    )


def test_table_output_and_critical_exit_code(
    mixed_response: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--exclude-mount", "/snap/*"], client=client_returning(mixed_response))
    out = capsys.readouterr().out
    assert code == 2
    assert out.splitlines()[0].split() == ["STATUS", "HOST", "MOUNT", "USED", "AVAILABLE", "SIZE"]
    assert "CRITICAL  db01" in out
    assert "/snap/core" not in out


def test_json_output(mixed_response: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--format", "json"], client=client_returning(mixed_response))
    data = json.loads(capsys.readouterr().out)
    assert code == 2
    assert data["status"] == "CRITICAL"
    assert len(data["results"]) == 5


def test_nagios_output_ok(capsys: pytest.CaptureFixture[str]) -> None:
    response = es_response({"web01": [mount("/", 0.40)]})
    code = main(["--format", "nagios"], client=client_returning(response))
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "FSMON OK - 1 file systems within thresholds | 'web01:/'=40.0%"


def test_nagios_output_warning_lists_problems(capsys: pytest.CaptureFixture[str]) -> None:
    response = es_response({"web01": [mount("/", 0.40), mount("/var", 0.85)]})
    code = main(["--format", "nagios"], client=client_returning(response))
    assert code == 1
    assert capsys.readouterr().out.startswith("FSMON WARNING - web01:/var 85.0%")


def test_no_data_is_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([], client=client_returning(es_response({})))
    assert code == 3
    assert "No file system data" in capsys.readouterr().out


def test_authentication_failure_is_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--format", "nagios"], client=client_returning({"error": {}}, status=401))
    assert code == 3
    assert "authentication failed" in capsys.readouterr().out


def test_search_error_reports_reason(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"error": {"reason": "no such index [metricbeat-*]"}}
    code = main([], client=client_returning(payload, status=404))
    assert code == 3
    assert "no such index" in capsys.readouterr().err


def test_custom_thresholds_and_request_shape() -> None:
    seen: list[httpx.Request] = []
    response = es_response({"web01": [mount("/", 0.85)]})
    code = main(
        ["--warning", "86", "--critical", "95", "--index", "metrics-*", "--since", "1h"],
        client=client_returning(response, seen=seen),
    )
    assert code == 0
    assert seen[0].url.path == "/metrics-*/_search"
    assert seen[0].headers["Authorization"] == "ApiKey secret"
    body = json.loads(seen[0].content)
    assert body["query"]["bool"]["filter"][0] == {"range": {"@timestamp": {"gte": "now-1h"}}}


def test_invalid_thresholds_exit_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--warning", "95", "--critical", "90"], client=client_returning({})) == 3
    assert "thresholds" in capsys.readouterr().err


def test_basic_auth_when_no_api_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=es_response({}))

    client = SearchClient(
        "http://es:9200", username="elastic", password="pw", transport=httpx.MockTransport(handler)
    )
    client.search("metricbeat-*", {"size": 0})
    assert seen[0].headers["Authorization"].startswith("Basic ")
    client.close()


def test_connection_error_is_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = SearchClient("http://es:9200", transport=httpx.MockTransport(handler))
    assert main([], client=client) == 3
    assert "cannot reach Elasticsearch" in capsys.readouterr().err
