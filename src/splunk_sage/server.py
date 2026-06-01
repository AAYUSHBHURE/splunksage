"""SplunkSage MCP Server — entry point.

Registers all MCP tools and starts the server over stdio so any
MCP-compatible client (Claude Desktop, Cursor, Claude Code, etc.)
can discover and call Splunk operations.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import settings
from .splunk_client import SplunkClient, SplunkError

# ─────────────────────────────────────────────────────────────────────────────
# Server + shared client
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "SplunkSage",
    instructions=(
        "You have access to a live Splunk instance via these tools. "
        "Use `ping_splunk` first to verify connectivity, then explore indexes "
        "with `list_indexes` before writing queries with `search_logs`. "
        "SPL (Splunk Processing Language) supports pipes, stats, eval, rex, "
        "timechart, and many more commands — use them freely."
    ),
)

_client = SplunkClient(
    host=settings.host,
    port=settings.port,
    token=settings.token,
    username=settings.username,
    password=settings.password,
    verify_ssl=settings.verify_ssl,
    timeout=settings.search_timeout,
)


def _err(msg: str) -> str:
    """Return a consistent error payload."""
    return json.dumps({"error": msg})


# ─────────────────────────────────────────────────────────────────────────────
# Tool: connectivity
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def ping_splunk() -> str:
    """Check connectivity to the Splunk instance and return server version info.

    Always call this first to verify the connection is working before
    running searches or managing alerts.

    Returns:
        JSON with Splunk version, build, product type, and server name.
    """
    try:
        return await _client.get_server_info()
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tool: search
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_logs(
    query: str,
    earliest_time: str = "-1h",
    latest_time: str = "now",
    max_results: int = 100,
) -> str:
    """Run a SPL (Splunk Processing Language) query and return results.

    Args:
        query: SPL query string. Examples:
            - 'index=main error | stats count by host'
            - 'index=web sourcetype=access_combined status=500 | timechart count'
            - 'index=_internal | head 20'
            You do NOT need to include the leading 'search' keyword.
        earliest_time: Start of search window. Relative: '-15m', '-1h', '-24h',
            '-7d'. Absolute ISO-8601: '2024-06-01T00:00:00'.
        latest_time: End of search window. Use 'now' for real-time, or same
            formats as earliest_time.
        max_results: Max rows to return (1–10 000). Default 100.

    Returns:
        JSON with fields list, result count, and array of result rows.
    """
    try:
        return await _client.search(query, earliest_time, latest_time, max_results)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: indexes
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_indexes() -> str:
    """List all enabled Splunk indexes with their event counts and disk sizes.

    Use this to discover which indexes exist before writing a search query.

    Returns:
        JSON with a list of indexes, each containing name, event count,
        disk size in MB, and earliest/latest event timestamps.
    """
    try:
        return await _client.list_indexes()
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def get_index_info(index_name: str) -> str:
    """Get detailed information about a specific Splunk index.

    Args:
        index_name: Exact name of the index (e.g. 'main', 'security', 'web').

    Returns:
        JSON with event count, disk size, retention period, hot bucket count,
        home path, and earliest/latest event timestamps.
    """
    try:
        return await _client.get_index_info(index_name)
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def get_field_summary(
    index: str = "main",
    earliest_time: str = "-24h",
    latest_time: str = "now",
) -> str:
    """Get a summary of all fields available in an index for a time window.

    Runs 'index=<name> | fieldsummary' to show you what fields are present,
    their data types, and how frequently they appear. Use this before writing
    complex queries so you know exactly which field names to reference.

    Args:
        index: Index name to summarize (default: 'main').
        earliest_time: Start of window (default: '-24h').
        latest_time: End of window (default: 'now').

    Returns:
        JSON with field names, types, counts, and sample values.
    """
    try:
        query = f"index={index} | fieldsummary maxvals=5"
        return await _client.search(query, earliest_time, latest_time, max_results=500)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: saved searches / reports
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_saved_searches() -> str:
    """List all saved searches and reports configured in Splunk.

    Returns:
        JSON with saved search names, SPL queries, descriptions, schedule
        info (cron expression, next run time), and whether each is scheduled.
    """
    try:
        return await _client.list_saved_searches()
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def run_saved_search(search_name: str) -> str:
    """Dispatch a saved search / report and return its results.

    Args:
        search_name: Exact name of the saved search (use list_saved_searches
            to discover names).

    Returns:
        JSON with search name, job SID, result count, and result rows.
    """
    try:
        return await _client.run_saved_search(search_name)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: alerts
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_alerts() -> str:
    """List all scheduled Splunk alerts with their status and schedule.

    Returns:
        JSON with alert names, SPL queries, cron schedules, last-fired times,
        severity levels, and descriptions.
    """
    try:
        return await _client.list_alerts()
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def create_alert(
    name: str,
    query: str,
    cron_schedule: str = "*/15 * * * *",
    condition: str = "search count > 0",
    description: str = "",
) -> str:
    """Create a new scheduled Splunk alert.

    Args:
        name: Unique name for the alert (no spaces; use underscores).
        query: SPL query to evaluate on each run.
            Example: 'index=security action=failed | stats count by src_ip'
        cron_schedule: When to run, in cron syntax (default: every 15 min).
            Examples: '0 * * * *' (hourly), '0 9 * * 1-5' (weekdays 9am).
        condition: Alert trigger condition (informational, stored as description).
            Example: 'count > 100'.
        description: Human-readable description of what this alert monitors.

    Returns:
        JSON confirming creation with name, query, and schedule.
    """
    try:
        return await _client.create_alert(name, query, cron_schedule, condition, description)
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def delete_alert(name: str) -> str:
    """Delete a Splunk saved search or alert by name.

    ⚠️  This is irreversible. Confirm the name with list_alerts first.

    Args:
        name: Exact name of the alert / saved search to delete.

    Returns:
        JSON confirming deletion.
    """
    try:
        return await _client.delete_alert(name)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: export
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def export_to_csv(
    query: str,
    output_path: str,
    earliest_time: str = "-1h",
    latest_time: str = "now",
    max_results: int = 10_000,
) -> str:
    """Run a SPL query and write the results to a local CSV file.

    Args:
        query: SPL query to run (same syntax as search_logs).
        output_path: Absolute path for the output file, e.g. 'C:/Users/me/errors.csv'.
            The directory must already exist.
        earliest_time: Start of search window (default: '-1h').
        latest_time: End of search window (default: 'now').
        max_results: Max rows to export (default: 10 000, max: 10 000).

    Returns:
        JSON confirming the file path, row count, and columns written.
    """
    import csv
    import os

    try:
        raw = await _client.search(query, earliest_time, latest_time, max_results)
        data = json.loads(raw)
        if "error" in data:
            return raw
        results = data.get("results", [])
        if not results:
            return json.dumps({"error": "Query returned no results — nothing to export."})

        # Build column list: user-facing fields first (no leading _), then internal
        fields = data.get("fields", list(results[0].keys()))
        visible = [f for f in fields if not f.startswith("_")]
        hidden = [f for f in fields if f.startswith("_")]
        columns = visible + hidden

        abs_path = os.path.abspath(output_path)
        with open(abs_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

        return json.dumps(
            {"status": "ok", "path": abs_path, "rows": len(results), "columns": columns},
            indent=2,
        )
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: multi-index search
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_multi_index(
    indexes: list[str],
    query: str,
    earliest_time: str = "-1h",
    latest_time: str = "now",
    max_results: int = 100,
) -> str:
    """Run a SPL query across multiple indexes simultaneously.

    Automatically constructs the correct SPL index filter so you don't
    have to remember the OR syntax.

    Args:
        indexes: List of index names to search across, e.g. ['main', 'security', '_audit'].
            Use list_indexes to discover available index names.
        query: The rest of the SPL after the index filter. Omit the index= clause.
            Example: 'log_level=ERROR | stats count by component | sort -count'
        earliest_time: Start of search window (default: '-1h').
        latest_time: End of search window (default: 'now').
        max_results: Max rows to return (default: 100).

    Returns:
        JSON with fields list, result count, and result rows — same as search_logs.
    """
    try:
        if not indexes:
            return _err("indexes list cannot be empty.")
        index_filter = " OR ".join(f"index={ix}" for ix in indexes)
        full_query = f"({index_filter}) {query}".strip()
        return await _client.search(full_query, earliest_time, latest_time, max_results)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: dashboards
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_dashboard_data(dashboard_name: str = "") -> str:
    """List Splunk dashboards and optionally run all panel queries for one dashboard.

    When called without a name, returns all dashboards and the SPL queries
    embedded in their panels — useful for discovery.

    When called with a specific dashboard name, runs every panel query and
    returns the live data for each panel.

    Args:
        dashboard_name: Exact name of the dashboard to run (leave empty to just list them).
            Use the 'name' field from a no-argument call to get exact names.

    Returns:
        Without a name: JSON list of dashboards with panel queries.
        With a name: JSON with each panel's query and its live result rows.
    """
    try:
        dashboards_raw = await _client.list_dashboards()
        dashboards = json.loads(dashboards_raw).get("dashboards", [])

        if not dashboard_name:
            return dashboards_raw

        match = next((d for d in dashboards if d["name"] == dashboard_name), None)
        if not match:
            names = [d["name"] for d in dashboards]
            return _err(f"Dashboard '{dashboard_name}' not found. Available: {names}")

        panel_results = []
        for i, q in enumerate(match["panel_queries"]):
            result_raw = await _client.search(q.strip(), earliest_time="-24h")
            result = json.loads(result_raw)
            panel_results.append({"panel": i + 1, "query": q.strip(), "data": result})

        return json.dumps(
            {"dashboard": dashboard_name, "panels": len(panel_results), "panel_results": panel_results},
            indent=2, default=str,
        )
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tools: quick diagnostics
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def top_errors(
    earliest_time: str = "-24h",
    latest_time: str = "now",
    limit: int = 20,
) -> str:
    """Show the top ERROR-level log entries grouped by component.

    A fast way to spot which Splunk internal components are generating the
    most errors without writing a full SPL query.

    Args:
        earliest_time: Start of window (default: '-24h').
        latest_time: End of window (default: 'now').
        limit: Number of top components to return (default: 20).

    Returns:
        JSON with component names and error counts, sorted descending.
    """
    try:
        query = (
            f"index=_internal log_level=ERROR "
            f"| stats count by component "
            f"| sort -count "
            f"| head {limit}"
        )
        return await _client.search(query, earliest_time, latest_time, max_results=limit)
    except SplunkError as exc:
        return _err(str(exc))


@mcp.tool()
async def anomaly_detection(
    index: str = "_internal",
    earliest_time: str = "-24h",
    latest_time: str = "now",
) -> str:
    """Run Splunk's built-in anomaly detection on an index to surface unusual patterns.

    Uses the `anomalydetection` SPL command which scores fields by how
    unexpected their values are relative to their historical distribution.
    Samples up to 5 000 events to stay within search timeouts on large indexes.
    High-scoring rows are the most anomalous events in the window.

    Args:
        index: Index to scan (default: '_internal').
        earliest_time: Start of window (default: '-24h').
        latest_time: End of window (default: 'now').

    Returns:
        JSON with the most anomalous events, each tagged with a p-value score.
    """
    try:
        query = f"index={index} | head 5000 | anomalydetection | sort -pctSuspicious | head 20"
        return await _client.search(query, earliest_time, latest_time, max_results=20)
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Start the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
