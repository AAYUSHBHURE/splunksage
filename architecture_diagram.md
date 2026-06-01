# SplunkSage — Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI Client Layer                              │
│                                                                     │
│   Claude Code (CLI)  ·  Claude Desktop  ·  Cursor  ·  Any MCP      │
│                                                                     │
│   User: "Search for errors in the last hour"                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │  MCP Protocol (stdio)
                               │  JSON-RPC tool calls & responses
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  SplunkSage MCP Server  (Python)                    │
│                  src/splunk_sage/server.py                          │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │    Search     │  │    Indexes    │  │   Alerts & Saved Search  │ │
│  │               │  │               │  │                          │ │
│  │ search_logs   │  │ list_indexes  │  │ list_alerts              │ │
│  │ search_multi  │  │ get_index_    │  │ create_alert             │ │
│  │  _index       │  │  info         │  │ delete_alert             │ │
│  │ export_to_csv │  │ get_field_    │  │ list_saved_searches      │ │
│  │               │  │  summary      │  │ run_saved_search         │ │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘ │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐                               │
│  │  Diagnostics  │  │  Dashboards   │                               │
│  │               │  │               │                               │
│  │ top_errors    │  │ get_dashboard │                               │
│  │ anomaly_      │  │  _data        │                               │
│  │  detection    │  │               │                               │
│  │ ping_splunk   │  │               │                               │
│  └──────────────┘  └───────────────┘                               │
│                                                                     │
│            FastMCP (official MCP Python SDK)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │  Async HTTP (httpx)
                               │  Authorization: Bearer <JWT token>
                               │  HTTPS port 8089
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Splunk REST API Layer                           │
│                                                                     │
│  POST /services/search/jobs          → dispatch SPL search job      │
│  GET  /services/search/jobs/{sid}    → poll job status              │
│  GET  /services/search/jobs/{sid}/results → fetch results           │
│  GET  /services/data/indexes         → list indexes                 │
│  GET  /services/saved/searches       → saved searches & alerts      │
│  POST /services/saved/searches       → create alert                 │
│  GET  /services/data/ui/views        → dashboards                   │
│  GET  /services/server/info          → server metadata              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Splunk Enterprise / Splunk Cloud Instance              │
│                                                                     │
│  Indexes: main, _internal, security, custom ...                     │
│  Saved Searches · Alerts · Dashboards · Field Extractions           │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **User → AI Agent**: Natural language query (e.g. "show top errors by component")
2. **AI Agent → MCP Server**: Structured tool call via MCP stdio transport
3. **MCP Server → Splunk**: Async HTTPS request to REST API with Bearer token auth
4. **Splunk → MCP Server**: Raw JSON results (polls until job `DONE`)
5. **MCP Server → AI Agent**: Parsed JSON with fields, count, result rows
6. **AI Agent → User**: Human-readable summary or follow-up actions

## Component Details

| Component | Technology | Purpose |
|---|---|---|
| MCP Server | Python 3.11, FastMCP | Exposes Splunk as 15 MCP tools |
| HTTP Client | `httpx` (async) | Non-blocking REST API calls |
| Config | `pydantic-settings` | Type-safe env var / `.env` loading |
| Auth | Splunk Bearer JWT | Token-based auth, no password in env |
| Transport | MCP stdio | Works with Claude Desktop, Claude Code, Cursor |
| AI Integration | Any MCP client | Claude, GPT, Gemini with MCP support |

## AI Integration Points

- **Tool discovery**: MCP client reads tool schemas at startup
- **Tool selection**: AI model chooses which tool(s) to call based on user intent
- **Multi-step reasoning**: AI chains calls (e.g. `list_indexes` → `get_field_summary` → `search_logs`)
- **Anomaly detection**: `anomaly_detection` tool uses Splunk's built-in ML (`anomalydetection` SPL command)
- **Natural language → SPL**: AI model translates user intent into valid SPL queries
