# Splunk MCP Bridge 🔍

> **Give any AI agent the power of Splunk** — search logs, manage alerts, explore indexes, and run saved searches using natural language through the [Model Context Protocol](https://modelcontextprotocol.io/).

Built for the **[Splunk Agentic Ops Hackathon](https://splunk.devpost.com)** · Track: Platform & Developer Experience · Bonus: MCP Server

---

## ✨ What it does

Splunk MCP Bridge is an MCP server that wraps the Splunk REST API and exposes it as a set of structured tools any MCP-compatible AI client can call:

| Tool | Description |
|---|---|
| `ping_splunk` | Verify connectivity & get server info |
| `search_logs` | Run any SPL query with time range & result limit |
| `list_indexes` | Discover available indexes with sizes & event counts |
| `get_index_info` | Deep-dive into a single index |
| `get_field_summary` | See all fields in an index — before you write a query |
| `list_saved_searches` | Browse existing saved searches & reports |
| `run_saved_search` | Dispatch a saved search & get results |
| `list_alerts` | View all scheduled alerts |
| `create_alert` | Create a new scheduled SPL alert |
| `delete_alert` | Remove an alert by name |

### Demo scenario

```
User → Claude: "Why did my payment service have spikes last night?"

Claude calls:
  1. list_indexes()               → finds "payments" index
  2. get_field_summary("payments", earliest_time="-12h")  → learns field names
  3. search_logs(
       "index=payments status=error | timechart count by error_type",
       earliest_time="-12h"
     )                            → returns spike data
  4. search_logs(
       "index=payments status=error | stats count by host | sort -count",
       earliest_time="-12h"
     )                            → identifies which hosts were affected

Claude → User: "Between 02:00–04:00 UTC, web-07 generated 94% of payment
  errors (3,412 events). The dominant error was 'DB_CONNECTION_TIMEOUT'.
  A deployment happened at 01:58 UTC. Want me to create an alert for this?"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Client Layer                          │
│                                                             │
│  Claude Desktop  ·  Claude Code  ·  Cursor  ·  Any MCP     │
└──────────────────────────┬──────────────────────────────────┘
                           │  MCP Protocol (stdio)
                           │  Tool calls & JSON responses
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               Splunk MCP Bridge MCP Server (Python)                  │
│                                                             │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────────────┐ │
│  │  search   │  │  indexes  │  │   alerts & saved search  │ │
│  │  _logs    │  │  (list,   │  │   (list, create, run,    │ │
│  │           │  │  get,     │  │    delete)               │ │
│  │  get_     │  │  summary) │  │                         │ │
│  │  field_   │  │           │  │                         │ │
│  │  summary  │  │           │  │                         │ │
│  └───────────┘  └───────────┘  └─────────────────────────┘ │
│                                                             │
│  SplunkClient  ──  async httpx  ──  Bearer token auth       │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTPS REST API  (port 8089)
                           │  Authorization: Bearer <token>
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Splunk Cloud Instance                       │
│                                                             │
│  /services/search/jobs          Search Jobs API            │
│  /services/data/indexes         Index Management           │
│  /services/saved/searches       Saved Searches & Alerts    │
│  /services/server/info          Server Metadata            │
└─────────────────────────────────────────────────────────────┘
```

### Technology choices

| Component | Choice | Why |
|---|---|---|
| MCP SDK | `mcp[cli]` (FastMCP) | Official Python SDK; decorator-based API |
| HTTP client | `httpx` | Async-native; no threading needed |
| Config | `pydantic-settings` | Type-safe env var loading with `.env` support |
| Auth | Bearer token | Recommended for Splunk Cloud; no password in env |
| Transport | stdio | Universal MCP transport; works in Claude Desktop, CLI, IDE |

---

## 🚀 Quick start

### Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- A Splunk Cloud account ([free trial](https://www.splunk.com/en_us/download/splunk-cloud.html))
- A Splunk auth token (see below)

### 1. Clone & install

```bash
git clone https://github.com/<you>/splunk-mcp-bridge.git
cd splunk-mcp-bridge
uv sync          # installs all dependencies into .venv
```

Or with pip:
```bash
pip install -e ".[dev]"
```

### 2. Get a Splunk auth token

1. Log in to your Splunk Cloud instance
2. Go to **Settings → Tokens → New Token**
3. Set audience to `Splunk MCP Bridge MCP` and no expiry (or a long one)
4. Copy the token value

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your Splunk host and token:
#   SPLUNK_HOST=mystack.splunkcloud.com
#   SPLUNK_PORT=8089
#   SPLUNK_TOKEN=eyJr...
```

### 4. Test the connection

```bash
uv run splunk-mcp-bridge
# Should start without errors (waiting for MCP client to connect)
```

Or run a quick connectivity test:
```bash
python -c "
import asyncio, json
from src.splunk_mcp_bridge.splunk_client import SplunkClient
from src.splunk_mcp_bridge.config import settings
c = SplunkClient(settings.host, settings.port, settings.token, settings.verify_ssl)
print(asyncio.run(c.get_server_info()))
"
```

---

## 🔌 Connecting to Claude

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "Splunk MCP Bridge": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/splunk-mcp-bridge", "splunk-mcp-bridge"],
      "env": {
        "SPLUNK_HOST": "mystack.splunkcloud.com",
        "SPLUNK_PORT": "8089",
        "SPLUNK_TOKEN": "your-token-here"
      }
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add Splunk MCP Bridge \
  -e SPLUNK_HOST=mystack.splunkcloud.com \
  -e SPLUNK_PORT=8089 \
  -e SPLUNK_TOKEN=your-token-here \
  -- uv run --project /path/to/splunk-mcp-bridge splunk-mcp-bridge
```

### Cursor

Go to **Cursor Settings → MCP → Add Server** and paste the same config as the Claude Desktop example.

---

## 🧪 Running tests

```bash
uv run pytest -v
```

Tests use `pytest-httpx` to mock the Splunk REST API — no live instance required.

---

## 📁 Project structure

```
splunk-mcp-bridge/
├── src/
│   └── splunk_mcp_bridge/
│       ├── __init__.py
│       ├── config.py          # Pydantic settings (env vars)
│       ├── splunk_client.py   # Async Splunk REST API client
│       └── server.py          # FastMCP server & tool definitions
├── tests/
│   └── test_tools.py          # Unit tests with mocked HTTP
├── .env.example               # Config template
├── pyproject.toml             # Project metadata & dependencies
└── README.md
```

---

## 🛠️ Example prompts to try

Once connected to Claude:

```
"List all indexes and tell me which one has the most data"

"Search for 500 errors in the last 6 hours and group by endpoint"

"Show me all fields available in the security index"

"Create an alert called high_login_failures that fires every 15 minutes
 when index=security action=failure | stats count | where count > 50"

"What saved searches do I have? Run the one about daily error summary"

"Show me a timechart of events by sourcetype for the last 24 hours
 in the main index"
```

---

## 🔒 Security notes

- **Never commit your `.env` file** — it contains your auth token (`.gitignore` already covers this)
- Use a **scoped token** with only the capabilities your agent needs (`search`, `list_storage_passwords` is not required)
- For production, consider rotating tokens regularly and using Splunk's token expiry feature

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

## 🙏 Acknowledgements

- [Model Context Protocol](https://modelcontextprotocol.io/) by Anthropic
- [Splunk REST API](https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTprolog) documentation
- Built for the [Splunk Agentic Ops Hackathon 2026](https://splunk.devpost.com)
