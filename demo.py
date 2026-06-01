"""
Demo: the three operations from the original request.
  1. List all indexes
  2. Search last 100 _internal events
  3. List saved searches
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

from splunk_mcp_bridge.splunk_client import SplunkClient

client = SplunkClient(
    host=os.getenv("SPLUNK_HOST"),
    port=int(os.getenv("SPLUNK_PORT", 8089)),
    token=os.getenv("SPLUNK_TOKEN", ""),
    username=os.getenv("SPLUNK_USERNAME", ""),
    password=os.getenv("SPLUNK_PASSWORD", ""),
    verify_ssl=True,
    timeout=60,
)


async def main():
    # ── 1. List indexes ───────────────────────────────────────────────────────
    print("=" * 60)
    print("1. INDEXES")
    print("=" * 60)
    idx = json.loads(await client.list_indexes())
    print(f"{'Name':<25} {'Events':>12} {'Size (MB)':>10}")
    print("-" * 50)
    for i in idx["indexes"]:
        print(f"{i['name']:<25} {i['total_event_count']:>12,} {i['current_db_size_mb']:>10}")
    print(f"\nTotal: {idx['count']} indexes\n")

    # ── 2. Last 100 _internal events ──────────────────────────────────────────
    print("=" * 60)
    print("2. LAST 100 _internal EVENTS")
    print("=" * 60)
    raw = json.loads(await client.search(
        query="index=_internal | head 100",
        earliest_time="-1h",
        latest_time="now",
        max_results=100,
    ))
    print(f"Results returned : {raw['result_count']}")
    print(f"Fields available : {', '.join(raw['fields'][:10])}{'...' if len(raw['fields']) > 10 else ''}")
    print()
    for i, row in enumerate(raw["results"][:5], 1):
        ts    = row.get("_time", "")[:19]
        src   = row.get("source", "")
        level = row.get("log_level", row.get("severity", ""))
        msg   = row.get("_raw", "")[:100].replace("\n", " ")
        print(f"  [{i}] {ts}  {level:<8}  {src}")
        print(f"       {msg}")
    if raw["result_count"] > 5:
        print(f"  ... and {raw['result_count'] - 5} more rows")
    print()

    # ── 3. Saved searches ─────────────────────────────────────────────────────
    print("=" * 60)
    print("3. SAVED SEARCHES")
    print("=" * 60)
    ss = json.loads(await client.list_saved_searches())
    print(f"Total saved searches: {ss['count']}\n")
    scheduled = [s for s in ss["saved_searches"] if s["is_scheduled"]]
    unscheduled = [s for s in ss["saved_searches"] if not s["is_scheduled"]]
    if scheduled:
        print(f"  Scheduled ({len(scheduled)}):")
        for s in scheduled:
            print(f"    - {s['name']}")
            print(f"        cron   : {s['cron_schedule']}")
            print(f"        query  : {s['query'][:80]}")
    if unscheduled:
        print(f"\n  Ad-hoc / reports ({len(unscheduled)}):")
        for s in unscheduled[:10]:
            print(f"    - {s['name']}")
            if s.get("description"):
                print(f"        desc   : {s['description'][:80]}")
        if len(unscheduled) > 10:
            print(f"    ... and {len(unscheduled) - 10} more")
    if ss["count"] == 0:
        print("  (none configured)")


if __name__ == "__main__":
    asyncio.run(main())
