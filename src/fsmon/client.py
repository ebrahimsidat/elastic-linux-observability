"""Minimal Elasticsearch search client (API key or basic authentication)."""

from __future__ import annotations

from typing import Any

import httpx


class ElasticsearchError(RuntimeError):
    """Raised when Elasticsearch cannot be reached or rejects the query."""


class SearchClient:
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify: bool | str = True,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth: httpx.BasicAuth | None = None
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        elif username:
            auth = httpx.BasicAuth(username, password or "")
        self._client = httpx.Client(
            base_url=url.rstrip("/"),
            headers=headers,
            auth=auth,
            verify=verify,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"/{index}/_search", json=body)
        except httpx.HTTPError as exc:
            raise ElasticsearchError(f"cannot reach Elasticsearch: {exc}") from exc
        if response.status_code in (401, 403):
            raise ElasticsearchError(f"authentication failed (HTTP {response.status_code})")
        if response.status_code >= 400:
            reason = ""
            try:
                reason = response.json().get("error", {}).get("reason", "")
            except (ValueError, AttributeError):
                reason = response.text[:200]
            raise ElasticsearchError(f"search failed (HTTP {response.status_code}): {reason}")
        data: dict[str, Any] = response.json()
        return data
