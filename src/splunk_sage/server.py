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
# Tool: incident investigation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def investigate_incident(
    description: str,
    earliest_time: str = "-1h",
    latest_time: str = "now",
    index_hint: str = "",
) -> str:
    """Autonomously investigate an incident by chaining multiple Splunk queries.

    Mimics what a senior SRE does when paged: finds where errors are spiking,
    identifies the start of the incident window, surfaces the top error messages,
    checks which hosts are affected, and looks for correlated system events
    (deploys, restarts, config changes) that may be the root cause.

    Args:
        description: Plain-English description of the issue.
            Example: "payment service latency spike", "login failures", "high CPU"
        earliest_time: Start of investigation window (default: '-1h').
        latest_time: End of investigation window (default: 'now').
        index_hint: Optional index name to focus on. If empty, all non-internal
            indexes are scanned automatically.

    Returns:
        JSON incident report with: affected indexes, spike timeline, top error
        messages, impacted hosts, correlated system events, and recommended
        next queries.
    """
    report: dict = {
        "description": description,
        "window": f"{earliest_time} → {latest_time}",
        "steps": [],
        "affected_indexes": [],
        "spike_timeline": {},
        "top_errors": {},
        "impacted_hosts": {},
        "system_events": [],
        "recommended_queries": [],
    }

    try:
        # ── Step 1: Determine target indexes ─────────────────────────────────
        if index_hint:
            target_indexes = [index_hint]
        else:
            raw = json.loads(await _client.list_indexes())
            target_indexes = [
                ix["name"] for ix in raw.get("indexes", [])
                if not ix["name"].startswith("_") and ix.get("total_event_count", 0) > 0
            ][:6]  # cap at 6 to avoid timeout

        report["steps"].append(f"Scanning {len(target_indexes)} index(es): {target_indexes}")

        # ── Step 2: Find indexes with elevated error activity ─────────────────
        error_pattern = "(error OR ERROR OR exception OR EXCEPTION OR fail OR FAIL OR critical OR CRITICAL OR fatal OR FATAL)"
        affected: list[dict] = []
        for idx in target_indexes:
            raw = json.loads(await _client.search(
                f"index={idx} {error_pattern} | stats count",
                earliest_time, latest_time, 1,
            ))
            count = int(raw.get("results", [{}])[0].get("count", 0))
            if count > 0:
                affected.append({"index": idx, "error_count": count})

        affected.sort(key=lambda x: x["error_count"], reverse=True)
        report["affected_indexes"] = affected
        report["steps"].append(
            f"Found errors in {len(affected)} index(es): "
            + ", ".join(f"{a['index']} ({a['error_count']})" for a in affected)
        )

        if not affected:
            report["steps"].append("No error patterns found — incident may not be error-based. "
                                   "Try searching for latency or throughput metrics.")
            return json.dumps(report, indent=2, default=str)

        top_indexes = [a["index"] for a in affected[:3]]

        # ── Step 3: Spike timeline — when did it start? ───────────────────────
        for idx in top_indexes:
            raw = json.loads(await _client.search(
                f"index={idx} {error_pattern} | timechart span=5m count",
                earliest_time, latest_time, 100,
            ))
            report["spike_timeline"][idx] = raw.get("results", [])

        report["steps"].append("Built 5-minute error timechart for top affected indexes")

        # ── Step 4: Top error messages ────────────────────────────────────────
        for idx in top_indexes:
            raw = json.loads(await _client.search(
                f"index={idx} {error_pattern} "
                f"| rex field=_raw \"(?i)(?:error|exception|fail|fatal)[:\\s]+(?P<msg>[^\\n]{{0,120}})\" "
                f"| stats count by msg | sort -count | head 10",
                earliest_time, latest_time, 10,
            ))
            report["top_errors"][idx] = raw.get("results", [])

        report["steps"].append("Extracted top error messages per index")

        # ── Step 5: Impacted hosts ────────────────────────────────────────────
        for idx in top_indexes:
            raw = json.loads(await _client.search(
                f"index={idx} {error_pattern} | stats count by host | sort -count | head 10",
                earliest_time, latest_time, 10,
            ))
            report["impacted_hosts"][idx] = raw.get("results", [])

        report["steps"].append("Identified impacted hosts per index")

        # ── Step 6: Correlated system events (deploys, restarts, config) ─────
        sys_raw = json.loads(await _client.search(
            "index=_internal sourcetype=splunkd "
            "(component=Scheduler OR component=Deployment OR component=Launcher OR "
            "component=ShutdownHandler OR \"config reload\" OR \"restarting\" OR "
            "\"application started\" OR \"application stopped\") "
            "| table _time component message | head 20",
            earliest_time, latest_time, 20,
        ))
        report["system_events"] = sys_raw.get("results", [])
        report["steps"].append(
            f"Found {len(report['system_events'])} correlated system event(s) "
            "(deploys, restarts, config reloads)"
        )

        # ── Step 7: Recommended follow-up queries ─────────────────────────────
        for idx in top_indexes:
            report["recommended_queries"].append(
                f"index={idx} {error_pattern} | rex field=_raw \"(?P<trace>[A-Z][a-z]+Exception[^\\n]*)\" "
                f"| stats count by trace | sort -count"
            )
            report["recommended_queries"].append(
                f"index={idx} {error_pattern} | timechart span=1m count by host"
            )

    except SplunkError as exc:
        return _err(str(exc))

    return json.dumps(report, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: SPL validation + explanation
# ─────────────────────────────────────────────────────────────────────────────

_SPL_DOCS: dict[str, str] = {
    "search": "Filters events matching keywords or field=value pairs. The implicit first command.",
    "stats": "Aggregates events into statistics (count, sum, avg, min, max, dc, etc.).",
    "chart": "Like stats but produces a table suitable for charting, with one column per value.",
    "timechart": "Time-series aggregation — one row per time bucket, great for trend graphs.",
    "eval": "Computes a new field or transforms an existing one using an expression.",
    "rex": "Extracts fields from raw text using a named-capture regex.",
    "where": "Filters results using an eval-style boolean expression (runs after aggregation).",
    "sort": "Orders results. Use `-field` for descending, `+field` for ascending.",
    "head": "Returns the first N results (equivalent to SQL LIMIT).",
    "tail": "Returns the last N results.",
    "table": "Projects specific columns; drops all others.",
    "fields": "Includes or excludes fields. `fields +f1,f2` keeps; `fields -f1` drops.",
    "rename": "Renames a field.",
    "dedup": "Removes duplicate events based on one or more field values.",
    "join": "Joins results with another search on a common field (expensive — prefer stats).",
    "append": "Appends results of a sub-search to the current result set.",
    "union": "Merges results from multiple datasets without deduplication.",
    "lookup": "Enriches events by joining against a CSV lookup table.",
    "inputlookup": "Reads a lookup table as a search source.",
    "outputlookup": "Writes results to a lookup table.",
    "tstats": "Ultra-fast stats over indexed fields — 10–100× faster than stats on large data.",
    "bucket": "Discretises a continuous field into buckets (alias: bin).",
    "bin": "Alias for bucket — groups numeric/time values into ranges.",
    "transaction": "Groups related events into transactions based on field values and time.",
    "eventstats": "Like stats but adds aggregated values back as fields on each original event.",
    "streamstats": "Running/windowed stats computed as events are streamed.",
    "predict": "Forecasts future values using historical data (Splunk ML Toolkit).",
    "anomalydetection": "Scores events by how unusual they are relative to their distribution.",
    "cluster": "Groups similar events using text similarity.",
    "rare": "Returns the least common values of a field.",
    "top": "Returns the most common values of a field with counts and percentages.",
    "strcat": "Concatenates field values into a new field.",
    "multikv": "Extracts key-value pairs from multi-value fields.",
    "xmlkv": "Extracts key-value pairs from XML-formatted fields.",
    "regex": "Filters events where a field matches (or does not match) a regex.",
    "return": "Returns results from a sub-search to the parent search.",
    "format": "Formats the output of a sub-search as a search string.",
    "mstats": "Queries metrics indexes — faster than stats for time-series metrics.",
}


def _explain_spl(spl: str) -> list[dict]:
    """Parse a SPL string into pipe stages and explain each one."""
    import re as _re

    # Split on pipes that are not inside parentheses or quotes
    stages: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    string_char = ""
    for char in spl:
        if in_string:
            current.append(char)
            if char == string_char:
                in_string = False
        elif char in ('"', "'"):
            in_string = True
            string_char = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "|" and depth == 0:
            stages.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        stages.append("".join(current).strip())

    explanations = []
    for i, stage in enumerate(stages):
        if not stage:
            continue
        cmd = _re.split(r"\s+", stage)[0].lower().lstrip("|").strip()
        description = _SPL_DOCS.get(cmd, f"SPL command `{cmd}` — see Splunk docs for details.")
        explanations.append({
            "stage": i + 1,
            "command": cmd,
            "full_text": stage,
            "explanation": description,
        })
    return explanations


def _performance_tips(spl: str) -> list[str]:
    """Return a list of actionable performance improvement suggestions."""
    import re as _re
    tips = []
    lower = spl.lower()

    if "index=*" in lower or "index = *" in lower:
        tips.append("Avoid `index=*` — searching all indexes is slow. Specify the index name explicitly.")

    if _re.search(r"\|\s*stats\b", lower) and not _re.search(r"earliest\s*=|latest\s*=", lower):
        tips.append("Add an `earliest=` / `latest=` time constraint before `stats` to limit scanned events.")

    if _re.search(r"\|\s*join\b", lower):
        tips.append("`join` is expensive for large datasets. Consider rewriting with `stats` + `eval` or a lookup.")

    if _re.search(r"\|\s*transaction\b", lower):
        tips.append("`transaction` is slower than `stats` for most grouping tasks. Use `stats` if you only need counts or field values per group.")

    if _re.search(r"\|\s*rex\b", lower) and not _re.search(r"\|\s*where\b|\|\s*search\b", lower):
        tips.append("If you use `rex` to filter events, add a `search` or `where` clause *before* `rex` to reduce the event set first.")

    if _re.search(r"search\s+\*\b", lower):
        tips.append("Avoid a bare `search *` — always filter by index, sourcetype, or keyword to reduce scan volume.")

    if _re.search(r"\|\s*stats\b.*\|\s*stats\b", lower):
        tips.append("Two consecutive `stats` commands can often be merged into one to avoid re-aggregating.")

    if "tstats" not in lower and _re.search(r"\|\s*stats\s+count\b", lower):
        tips.append("If the fields you're aggregating are indexed, `tstats` can be 10–100× faster than `stats`.")

    if not tips:
        tips.append("No obvious performance issues found.")

    return tips


@mcp.tool()
async def spl_validate_and_explain(query: str) -> str:
    """Validate a SPL query against Splunk, explain each pipe stage, and suggest optimizations.

    Three things in one call:
    1. **Validation** — runs the query with a 1-result limit to catch syntax errors before
       you use it in a saved search or alert.
    2. **Explanation** — breaks the query into pipe stages and explains what each one does
       in plain English, with the SPL command name and its purpose.
    3. **Performance tips** — static analysis that flags common slow patterns
       (index=*, expensive join/transaction, missing time filters, etc.).

    Args:
        query: SPL query string to validate and explain.
            Can include or omit the leading `search` keyword.
            Example: 'index=main error | stats count by host | sort -count'

    Returns:
        JSON with:
          - valid: whether the query parsed and ran without error
          - error: error message if invalid, null if valid
          - fields: list of output field names returned by the query
          - stages: per-pipe explanation list (stage number, command, explanation)
          - performance_tips: list of optimization suggestions
    """
    try:
        validation = await _client.validate_spl(query)
        stages = _explain_spl(query)
        tips = _performance_tips(query)

        return json.dumps(
            {
                "valid": validation["valid"],
                "error": validation.get("error"),
                "fields": validation.get("fields", []),
                "result_count_sample": validation.get("result_count", 0),
                "stages": stages,
                "performance_tips": tips,
            },
            indent=2,
        )
    except SplunkError as exc:
        return _err(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tool: deployment health check
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
async def deployment_health_check() -> str:
    """Run a comprehensive health check on the Splunk deployment.

    Checks six dimensions and produces an overall health score (0–100):

    1. **License** — quota consumed today (warn >80%, critical >95%)
    2. **Indexing** — events ingested in the last 15 minutes from _internal metrics
    3. **Errors** — ERROR-level log rate in _internal over the last hour
    4. **Search load** — number of currently running search jobs
    5. **KV Store** — kvstore health status
    6. **Index health** — any disabled or empty indexes

    Returns:
        JSON with per-dimension status, score, findings, and an overall
        health_score (100 = fully healthy, lower = issues found).
    """
    try:
        findings: list[dict] = []
        score = 100

        # ── 1. License ────────────────────────────────────────────────────────
        lic = await _client.get_license_info()
        lic_status = "ok"
        for pool in lic.get("pools", []):
            pct = pool.get("used_pct", 0)
            if pct >= 95:
                lic_status = "critical"
                score -= 25
                findings.append({
                    "dimension": "license",
                    "severity": "critical",
                    "message": f"Pool '{pool['pool']}' is {pct}% full "
                               f"({pool['used_gb']} GB / {pool['quota_gb']} GB)",
                })
            elif pct >= 80:
                lic_status = "warning"
                score -= 10
                findings.append({
                    "dimension": "license",
                    "severity": "warning",
                    "message": f"Pool '{pool['pool']}' is {pct}% full — approaching limit",
                })

        # ── 2. Indexing rate ──────────────────────────────────────────────────
        rate_raw = json.loads(await _client.search(
            "index=_internal sourcetype=splunk_resource_usage component=Metrics "
            "group=per_index_thruput series!=_* "
            "| stats sum(kb) as kb_15m | eval mbps=round(kb_15m/1024/15/60,2)",
            "-15m", "now", 1,
        ))
        mbps = 0.0
        if rate_raw.get("results"):
            mbps = float(rate_raw["results"][0].get("mbps") or 0)

        indexing_status = "ok"
        if mbps == 0:
            indexing_status = "warning"
            score -= 10
            findings.append({
                "dimension": "indexing",
                "severity": "warning",
                "message": "No indexing activity detected in the last 15 minutes — "
                           "forwarders may be disconnected.",
            })

        # ── 3. Internal error rate ────────────────────────────────────────────
        err_raw = json.loads(await _client.search(
            "index=_internal log_level=ERROR | stats count by component | sort -count | head 10",
            "-1h", "now", 10,
        ))
        error_results = err_raw.get("results", [])
        total_errors = sum(int(r.get("count", 0)) for r in error_results)
        error_status = "ok"
        if total_errors > 500:
            error_status = "critical"
            score -= 20
            findings.append({
                "dimension": "errors",
                "severity": "critical",
                "message": f"{total_errors} internal errors in the last hour. "
                           f"Top component: {error_results[0]['component'] if error_results else 'unknown'}",
            })
        elif total_errors > 100:
            error_status = "warning"
            score -= 8
            findings.append({
                "dimension": "errors",
                "severity": "warning",
                "message": f"{total_errors} internal errors in the last hour",
            })

        # ── 4. Search load ────────────────────────────────────────────────────
        jobs = await _client.get_active_searches()
        active_count = jobs.get("active_job_count", 0)
        search_status = "ok"
        if active_count > 20:
            search_status = "warning"
            score -= 10
            findings.append({
                "dimension": "search_load",
                "severity": "warning",
                "message": f"{active_count} searches currently running — "
                           "high concurrency may impact performance.",
            })

        # ── 5. KV Store ───────────────────────────────────────────────────────
        kv = await _client.get_kv_store_status()
        kv_status = kv.get("status", "unavailable")
        if kv_status not in ("ready", "unavailable"):
            score -= 15
            findings.append({
                "dimension": "kvstore",
                "severity": "critical",
                "message": f"KV Store status is '{kv_status}' — apps relying on lookups may be broken.",
            })

        # ── 6. Index health ───────────────────────────────────────────────────
        idx_raw = json.loads(await _client.list_indexes())
        all_indexes = idx_raw.get("indexes", [])
        empty_indexes = [ix["name"] for ix in all_indexes if ix.get("total_event_count", 0) == 0]
        index_status = "ok"
        if empty_indexes:
            index_status = "warning"
            score -= 5
            findings.append({
                "dimension": "indexes",
                "severity": "warning",
                "message": f"{len(empty_indexes)} empty index(es): {empty_indexes[:5]}",
            })

        score = max(0, score)

        if score >= 90:
            overall = "healthy"
        elif score >= 70:
            overall = "degraded"
        elif score >= 50:
            overall = "unhealthy"
        else:
            overall = "critical"

        return json.dumps(
            {
                "health_score": score,
                "overall_status": overall,
                "dimensions": {
                    "license": {"status": lic_status, "pools": lic.get("pools", [])},
                    "indexing": {"status": indexing_status, "throughput_mbps": mbps},
                    "errors": {
                        "status": error_status,
                        "total_errors_1h": total_errors,
                        "top_components": error_results[:5],
                    },
                    "search_load": {"status": search_status, "active_jobs": active_count},
                    "kvstore": {"status": kv_status, "details": kv},
                    "indexes": {
                        "status": index_status,
                        "total": len(all_indexes),
                        "empty": empty_indexes,
                    },
                },
                "findings": findings,
                "checked_at": latest_time if (latest_time := "now") else "now",
            },
            indent=2,
            default=str,
        )
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
