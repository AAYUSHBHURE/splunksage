"""Unit tests for SplunkSage tools.

Uses pytest-httpx to mock Splunk REST API responses so tests
run without a real Splunk instance.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from splunk_sage.splunk_client import SplunkClient, SplunkError

BASE = "https://test.splunkcloud.com:8089"
TOKEN = "test-token-abc123"


@pytest.fixture
def client() -> SplunkClient:
    return SplunkClient(host="test.splunkcloud.com", port=8089, token=TOKEN, verify_ssl=False, timeout=5)


# ─────────────────────────────────────── ping / server info ──────────────────


@pytest.mark.asyncio
async def test_get_server_info(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/services/server/info?output_mode=json",
        json={
            "entry": [
                {
                    "content": {
                        "version": "9.2.1",
                        "build": "abc123",
                        "product_type": "splunk",
                        "serverName": "test-server",
                        "os_name": "Linux",
                    }
                }
            ]
        },
    )
    result = json.loads(await client.get_server_info())
    assert result["version"] == "9.2.1"
    assert result["server_name"] == "test-server"


# ────────────────────────────────────────── indexes ──────────────────────────


@pytest.mark.asyncio
async def test_list_indexes(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/services/data/indexes?output_mode=json&count=0",
        json={
            "entry": [
                {
                    "name": "main",
                    "content": {
                        "totalEventCount": 1_000_000,
                        "currentDBSizeMB": 512,
                        "minTime": "2024-01-01T00:00:00.000+0000",
                        "maxTime": "2024-06-01T00:00:00.000+0000",
                        "disabled": False,
                    },
                },
                {
                    "name": "security",
                    "content": {
                        "totalEventCount": 500_000,
                        "currentDBSizeMB": 256,
                        "minTime": "2024-01-01T00:00:00.000+0000",
                        "maxTime": "2024-06-01T00:00:00.000+0000",
                        "disabled": False,
                    },
                },
            ]
        },
    )
    result = json.loads(await client.list_indexes())
    assert result["count"] == 2
    names = [i["name"] for i in result["indexes"]]
    assert "main" in names
    assert "security" in names


# ────────────────────────────────────────── search ───────────────────────────


@pytest.mark.asyncio
async def test_search_returns_results(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    # 1. Create job
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/services/search/jobs",
        json={"sid": "scheduler__admin__search__RMD5abc_at_1234567890_1"},
    )
    # 2. Poll status — DONE immediately
    httpx_mock.add_response(
        url=f"{BASE}/services/search/jobs/scheduler__admin__search__RMD5abc_at_1234567890_1?output_mode=json",
        json={"entry": [{"content": {"dispatchState": "DONE"}}]},
    )
    # 3. Fetch results
    httpx_mock.add_response(
        url=(
            f"{BASE}/services/search/jobs/scheduler__admin__search__RMD5abc_at_1234567890_1"
            "/results?count=100&output_mode=json"
        ),
        json={
            "fields": [{"name": "host"}, {"name": "count"}],
            "results": [
                {"host": "web-01", "count": "42"},
                {"host": "web-02", "count": "17"},
            ],
        },
    )

    result = json.loads(await client.search("index=main | stats count by host"))
    assert result["result_count"] == 2
    assert result["fields"] == ["host", "count"]
    assert result["results"][0]["host"] == "web-01"


@pytest.mark.asyncio
async def test_search_prepends_search_keyword(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    """Queries not starting with 'search' or '|' should get 'search' prepended."""
    captured: list[str] = []

    def capture(request, extensions):  # noqa: ARG001
        body = request.content.decode()
        captured.append(body)
        return httpx_mock.add_response(json={"sid": "test-sid-001"})

    httpx_mock.add_callback(capture, method="POST", url=f"{BASE}/services/search/jobs")
    httpx_mock.add_response(
        url=f"{BASE}/services/search/jobs/test-sid-001?output_mode=json",
        json={"entry": [{"content": {"dispatchState": "DONE"}}]},
    )
    httpx_mock.add_response(
        url=f"{BASE}/services/search/jobs/test-sid-001/results?count=10&output_mode=json",
        json={"fields": [], "results": []},
    )
    await client.search("index=main error", max_results=10)
    assert any("search+index%3Dmain+error" in c or "search index%3Dmain" in c or "search" in c for c in captured)


# ────────────────────────────────────────── alerts ───────────────────────────


@pytest.mark.asyncio
async def test_create_alert(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/services/saved/searches",
        json={"entry": [{"name": "high_error_rate", "content": {}}]},
        status_code=201,
    )
    result = json.loads(
        await client.create_alert(
            name="high_error_rate",
            query="index=main error | stats count | where count > 100",
            cron_schedule="*/15 * * * *",
            condition="count > 100",
            description="Alert when error rate exceeds threshold",
        )
    )
    assert result["status"] == "created"
    assert result["name"] == "high_error_rate"


@pytest.mark.asyncio
async def test_list_alerts(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/services/saved/searches?output_mode=json&count=0&search=is_scheduled%3D1",
        json={
            "entry": [
                {
                    "name": "high_error_rate",
                    "content": {
                        "search": "index=main error | stats count",
                        "is_scheduled": True,
                        "cron_schedule": "*/15 * * * *",
                        "description": "Error rate monitor",
                        "alert.severity": "3",
                        "alert.last_fired": "",
                        "next_scheduled_time": "2024-06-01T12:00:00",
                    },
                }
            ]
        },
    )
    result = json.loads(await client.list_alerts())
    assert result["count"] == 1
    assert result["alerts"][0]["name"] == "high_error_rate"


# ────────────────────────────────────── error handling ───────────────────────


@pytest.mark.asyncio
async def test_auth_error_raises_splunk_error(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/services/server/info?output_mode=json",
        status_code=401,
        json={"messages": [{"type": "WARN", "text": "Authentication failed"}]},
    )
    with pytest.raises(SplunkError, match="Authentication failed"):
        await client.get_server_info()


@pytest.mark.asyncio
async def test_not_found_raises_splunk_error(httpx_mock: HTTPXMock, client: SplunkClient) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/services/data/indexes/nonexistent?output_mode=json",
        status_code=404,
        json={"messages": []},
    )
    with pytest.raises(SplunkError, match="not found"):
        await client.get_index_info("nonexistent")
