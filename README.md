# SplunkSage — Agentic Ops for Splunk

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-stdio-purple?logo=anthropic)
![Splunk](https://img.shields.io/badge/Splunk-Enterprise%20%7C%20Cloud-ff6600?logo=splunk)
![Hackathon](https://img.shields.io/badge/Splunk%20Agentic%20Ops%20Hackathon-2026-red)

> **Give any AI agent the full power of Splunk** — search logs, manage alerts, explore indexes, detect anomalies, and export data using natural language through the [Model Context Protocol](https://modelcontextprotocol.io/).

Built for the **[Splunk Agentic Ops Hackathon 2026](https://splunk.devpost.com)** · Track: **Platform & Developer Experience** · Bonus: **Best Use of Splunk MCP Server**

---

## Overview

SplunkSage is a production-ready MCP server that wraps the Splunk REST API and exposes it as 15 structured tools any MCP-compatible AI client can call. It works with both **Splunk Enterprise** (port 8089, Bearer token) and **Splunk Cloud** (port 443, session auth) — automatically selecting the right connection mode.

```
User → "Why did my payment service spike at 2am?"

Claude calls:
  1. list_indexes()                              → finds "payments" index
  2. get_field_summary("payments", "-12h")       → learns available fields
  3. search_logs("index=payments status=error
      | timechart count by error_type", "-12h")  → spike data
  4. search_logs("index=payments status=error
      | stats count by host | sort -count")      → which hosts failed

Claude → "web-07 generated 94% of errors (3,412 events).
  Root cause: DB_CONNECTION_TIMEOUT after deploy at 01:58 UTC.
  Want me to create an alert for this?"
```

---

## Tools

| Tool | Description |
|---|---|
| `ping_splunk` | Verify connectivity and get server version info |
| `search_logs` | Run any SPL query with time range and result limit |
| `search_multi_index` | Run SPL across multiple indexes simultaneously |
| `list_indexes` | Discover indexes with event counts and disk sizes |
| `get_index_info` | Deep-dive metadata for a single index |
| `get_field_summary` | See all fields in an index before writing a query |
| `list_saved_searches` | Browse saved searches and reports |
| `run_saved_search` | Dispatch a saved search and return live results |
| `list_alerts` | View all scheduled alerts with status and schedule |
| `create_alert` | Create a new scheduled SPL alert |
| `delete_alert` | Remove an alert by name |
| `export_to_csv` | Run a query and write results to a local CSV file |
| `get_dashboard_data` | List dashboards or run all panels for one dashboard |
| `top_errors` | Show top ERROR-level log entries grouped by component |
| `anomaly_detection` | Surface unusual patterns using Splunk's built-in ML |

---

## Quick Start

### Prerequisites
- Python 3.11+
- A Splunk Enterprise or Splunk Cloud instance
- A Splunk auth token (Settings → Tokens → New Token)

### 1. Clone & install

```bash
git clone https://github.com/AAYUSHBHURE/splunksage.git
cd splunksage
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
SPLUNK_HOST=localhost          # or mystack.splunkcloud.com
SPLUNK_PORT=8089
SPLUNK_TOKEN=eyJr...           # your Bearer token
SPLUNK_VERIFY_SSL=false        # true for production
```

### 3. Verify connection

```bash
python -c "
import asyncio
from src.splunk_sage.splunk_client import SplunkClient
from src.splunk_sage.config import settings
c = SplunkClient(settings.host, settings.port, settings.token,
                 settings.username, settings.password, settings.verify_ssl)
print(asyncio.run(c.get_server_info()))
"
```

---

## MCP Client Setup

### Claude Code (CLI)

```bash
claude mcp add -s user \
  -e SPLUNK_HOST=localhost \
  -e SPLUNK_PORT=8089 \
  -e SPLUNK_TOKEN=your-token-here \
  -e SPLUNK_VERIFY_SSL=false \
  splunksage -- python -m splunk_sage.server
```

### Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "splunksage": {
      "command": "python",
      "args": ["-m", "splunk_sage.server"],
      "env": {
        "SPLUNK_HOST": "localhost",
        "SPLUNK_PORT": "8089",
        "SPLUNK_TOKEN": "your-token-here",
        "SPLUNK_VERIFY_SSL": "false",
        "PYTHONPATH": "/path/to/splunksage/src"
      }
    }
  }
}
```

### Cursor

Go to **Cursor Settings → MCP → Add Server** and use the same JSON config as Claude Desktop.

---

## Connection Modes

SplunkSage auto-selects the right connection method:

| Mode | When | Auth |
|---|---|---|
| **A** — Direct REST (port 8089) | Splunk Enterprise, allowlisted Cloud | Bearer token |
| **B** — Web session (port 443) | Splunk Cloud free trial | Username + password |

Mode B activates automatically if Mode A fails — no configuration needed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      AI Client Layer                         │
│  Claude Code  ·  Claude Desktop  ·  Cursor  ·  Any MCP      │
└─────────────────────────┬────────────────────────────────────┘
                          │  MCP stdio (JSON-RPC)
                          ▼
┌──────────────────────────────────────────────────────────────┐
│              SplunkSage MCP Server  (Python)                 │
│              src/splunk_sage/server.py  ·  FastMCP           │
│                                                              │
│  search · multi-index · indexes · alerts · dashboards        │
│  saved searches · anomaly detection · CSV export             │
└─────────────────────────┬────────────────────────────────────┘
                          │  HTTPS (httpx async)
                          │  Bearer token  ·  port 8089 / 443
                          ▼
┌──────────────────────────────────────────────────────────────┐
│           Splunk Enterprise / Splunk Cloud Instance          │
│  Search Jobs  ·  Indexes  ·  Saved Searches  ·  Dashboards  │
└──────────────────────────────────────────────────────────────┘
```

See [architecture_diagram.md](architecture_diagram.md) for the full diagram with data flow details.

---

## Project Structure

```
splunksage/
├── src/
│   └── splunk_sage/
│       ├── server.py          # FastMCP server — 15 tool definitions
│       ├── splunk_client.py   # Async REST client (dual-mode auth)
│       ├── config.py          # Pydantic settings from env vars
│       └── __init__.py
├── tests/
│   └── test_tools.py          # Unit tests with mocked HTTP
├── .env.example               # Config template
├── .gitignore
├── architecture_diagram.md    # Full system architecture
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## Example Prompts

Once connected to Claude:

```
"List all indexes and tell me which has the most data"

"Search for HTTP 500 errors in the last 6 hours, group by endpoint"

"What fields are available in the security index?"

"Create an alert that fires every 15 minutes when
 index=security action=failure | stats count | where count > 50"

"Run the saved search called 'Daily Error Summary'"

"Show me a timechart of events by sourcetype for the last 24 hours"

"Detect anomalies in the main index over the last 24 hours"

"Export all errors from the last hour to C:/Users/me/errors.csv"
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

Tests use `pytest-httpx` to mock the Splunk REST API — no live Splunk instance required.

---

## Security

- **Never commit `.env`** — it's in `.gitignore`
- Use a **scoped token** with only the permissions your agent needs
- For production, enable `SPLUNK_VERIFY_SSL=true` and rotate tokens regularly

---

## Contributing

Pull requests welcome. Open an issue first for major changes.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-tool`)
3. Add tests for new tools
4. Submit a PR

---

## License

MIT — see [LICENSE](LICENSE)

---

## Acknowledgements

- [Model Context Protocol](https://modelcontextprotocol.io/) by Anthropic
- [Splunk REST API](https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTprolog)
- Built for the [Splunk Agentic Ops Hackathon 2026](https://splunk.devpost.com)
