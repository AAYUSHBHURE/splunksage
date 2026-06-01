"""Async Splunk REST API client.

Supports two connection modes automatically:
  - MODE A (port 8089, Bearer token): for self-hosted Enterprise + allowlisted Cloud
  - MODE B (port 443, session auth):  for Splunk Cloud free trials (no port 8089 access)

The client auto-selects mode B if mode A fails to connect.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx


class SplunkError(Exception):
    """Raised when the Splunk API returns an error."""


class SplunkClient:
    """Async client that works against both Splunk Enterprise (port 8089)
    and Splunk Cloud free-tier (port 443 via web session)."""

    def __init__(
        self,
        host: str,
        port: int = 8089,
        token: str = "",
        username: str = "",
        password: str = "",
        verify_ssl: bool = True,
        timeout: int = 60,
    ) -> None:
        self._host = host
        self._port = port
        self._token = token
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self.timeout = timeout

        # Set after _connect() resolves which mode works
        self._mode: str | None = None          # "direct" | "web"
        self._base_url: str = f"https://{host}:{port}"
        self._csrf_token: str = ""             # splunkweb_csrf_token_* (web mode only)
        self._web_base: str = f"https://{host}"
        self._session_cookies: dict = {}

    # ─────────────────────────── Connection bootstrap ─────────────────────────

    async def _connect(self) -> None:
        """Try port 8089 first; fall back to port 443 session auth."""
        if self._mode is not None:
            return  # already resolved

        # Mode A — direct REST API on port 8089
        if self._token:
            try:
                async with httpx.AsyncClient(verify=self._verify_ssl, timeout=8.0) as c:
                    r = await c.get(
                        f"{self._base_url}/services/server/info",
                        headers={"Authorization": f"Bearer {self._token}"},
                        params={"output_mode": "json"},
                    )
                    if r.status_code == 200:
                        self._mode = "direct"
                        return
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
                pass  # port 8089 blocked, try mode B

        # Mode B — session auth through port 443 web proxy
        if self._username and self._password:
            await self._web_login()
            self._mode = "web"
            return

        raise SplunkError(
            "Cannot connect to Splunk. "
            "Port 8089 is blocked and no username/password provided for web auth. "
            "Set SPLUNK_USERNAME and SPLUNK_PASSWORD in .env, or allowlist port 8089."
        )

    async def _web_login(self) -> None:
        """Authenticate via Splunk Web (port 443) and store session cookies."""
        login_url = f"{self._web_base}/en-US/account/login"

        async with httpx.AsyncClient(verify=self._verify_ssl, timeout=15.0, follow_redirects=True) as c:
            # Step 1: GET login page to harvest cval CSRF token
            r = await c.get(login_url)
            cval = ""
            # cval is in a cookie called "cval"
            if "cval" in c.cookies:
                cval = c.cookies["cval"]
            else:
                # Try to parse from HTML form
                m = re.search(r'name="cval"\s+value="([^"]+)"', r.text)
                if m:
                    cval = m.group(1)

            # Step 2: POST credentials
            payload = {
                "username": self._username,
                "password": self._password,
                "set_has_logged_in": "false",
                "return_to": "/en-US/",
            }
            if cval:
                payload["cval"] = cval

            r2 = await c.post(login_url, data=payload)
            if r2.status_code not in (200, 303) and "splunkweb_uid" not in c.cookies:
                raise SplunkError(
                    f"Splunk web login failed (HTTP {r2.status_code}). "
                    "Check SPLUNK_USERNAME and SPLUNK_PASSWORD."
                )

            # Collect all session cookies
            self._session_cookies = dict(c.cookies)

            # Splunk Cloud exposes the CSRF token as a cookie named
            # splunkweb_csrf_token_<port> — it must be sent as the
            # X-Splunk-Form-Key header on every POST/DELETE request.
            # The cookie is set after the first page load post-login.
            if not any(k.startswith("splunkweb_csrf_token") for k in c.cookies):
                await c.get(f"{self._web_base}/en-US/")

            self._csrf_token = ""
            for k, v in c.cookies.items():
                if k.startswith("splunkweb_csrf_token"):
                    self._csrf_token = v
                    break

    # ─────────────────────────── Low-level helpers ────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        await self._connect()
        merged = {"output_mode": "json", **(params or {})}

        if self._mode == "direct":
            url = f"{self._base_url}{path}"
            headers = {"Authorization": f"Bearer {self._token}"}
            cookies = {}
        else:
            url = f"{self._web_base}/en-US/splunkd/__raw{path}"
            headers = {"X-Requested-With": "XMLHttpRequest"}
            cookies = self._session_cookies

        async with httpx.AsyncClient(verify=self._verify_ssl, timeout=30.0, follow_redirects=False) as c:
            resp = await c.get(url, headers=headers, params=merged, cookies=cookies)
            if resp.status_code == 303 and self._mode == "web":
                # Session expired — re-login and retry once
                await self._web_login()
                cookies = self._session_cookies
                resp = await c.get(url, headers=headers, params=merged, cookies=cookies)
            self._raise_for_status(resp)
            return resp.json()

    async def _post(self, path: str, data: dict[str, Any]) -> dict:
        await self._connect()
        merged = {"output_mode": "json", **data}

        if self._mode == "direct":
            url = f"{self._base_url}{path}"
            headers = {"Authorization": f"Bearer {self._token}"}
            cookies = {}
        else:
            url = f"{self._web_base}/en-US/splunkd/__raw{path}"
            # Splunk Cloud requires the CSRF token as X-Splunk-Form-Key
            # on every POST; it comes from the splunkweb_csrf_token_* cookie.
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "X-Splunk-Form-Key": self._csrf_token,
            }
            cookies = self._session_cookies

        async with httpx.AsyncClient(verify=self._verify_ssl, timeout=30.0, follow_redirects=False) as c:
            resp = await c.post(url, headers=headers, data=merged, cookies=cookies)
            if resp.status_code == 303 and self._mode == "web":
                await self._web_login()
                cookies = self._session_cookies
                headers["X-Splunk-Form-Key"] = self._csrf_token
                resp = await c.post(url, headers=headers, data=merged, cookies=cookies)
            self._raise_for_status(resp)
            return resp.json()

    async def _delete(self, path: str) -> dict:
        await self._connect()
        if self._mode == "direct":
            url = f"{self._base_url}{path}"
            headers = {"Authorization": f"Bearer {self._token}"}
            cookies = {}
        else:
            url = f"{self._web_base}/en-US/splunkd/__raw{path}"
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "X-Splunk-Form-Key": self._csrf_token,
            }
            cookies = self._session_cookies

        async with httpx.AsyncClient(verify=self._verify_ssl, timeout=30.0, follow_redirects=False) as c:
            resp = await c.delete(url, headers=headers, params={"output_mode": "json"}, cookies=cookies)
            self._raise_for_status(resp)
            return resp.json()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise SplunkError(
                "Authentication failed — check your SPLUNK_TOKEN or credentials. "
                "If using web mode, verify SPLUNK_USERNAME and SPLUNK_PASSWORD are correct."
            )
        if resp.status_code == 403:
            raise SplunkError(
                "Permission denied — the token/user lacks required capabilities. "
                "In Splunk: Settings > Users > your user > ensure 'search' and "
                "'indexes_list_all' capabilities are granted."
            )
        if resp.status_code == 404:
            raise SplunkError(
                f"Resource not found: {resp.url.path} — the index, saved search, or "
                "alert name may be misspelled. Use list_indexes or list_saved_searches to confirm."
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
                messages = body.get("messages", [])
                detail = "; ".join(m.get("text", "") for m in messages) or resp.text
            except Exception:
                detail = resp.text[:300]
            raise SplunkError(f"Splunk API error {resp.status_code}: {detail}")

    # ─────────────────────────────── Search helpers ───────────────────────────

    async def _wait_for_job(self, sid: str) -> str:
        for _ in range(self.timeout):
            data = await self._get(f"/services/search/jobs/{sid}")
            state = data["entry"][0]["content"]["dispatchState"]
            if state in ("DONE", "FAILED", "PAUSED", "FINALIZED"):
                return state
            await asyncio.sleep(1)
        return "TIMEOUT"

    # ─────────────────────────────── Public API ───────────────────────────────

    async def get_connection_mode(self) -> str:
        """Return which connection mode is active ('direct' or 'web')."""
        await self._connect()
        return self._mode or "unknown"

    async def search(
        self,
        query: str,
        earliest_time: str = "-1h",
        latest_time: str = "now",
        max_results: int = 100,
    ) -> str:
        spl = query.strip()
        if not spl.startswith(("search ", "|")):
            spl = f"search {spl}"

        # Try oneshot first — results come back in a single POST, no polling needed.
        # Falls back to async job mode if the server rejects oneshot (e.g. real-time windows).
        try:
            resp = await self._post(
                "/services/search/jobs",
                {
                    "search": spl,
                    "earliest_time": earliest_time,
                    "latest_time": latest_time,
                    "exec_mode": "oneshot",
                    "count": str(min(max_results, 10_000)),
                    "output_mode": "json",
                },
            )
            results = resp.get("results", [])
            fields = [f["name"] for f in resp.get("fields", [])]
            return json.dumps(
                {"mode": "oneshot", "result_count": len(results), "fields": fields, "results": results},
                indent=2, default=str,
            )
        except SplunkError:
            pass  # fall through to async job mode

        job = await self._post(
            "/services/search/jobs",
            {
                "search": spl,
                "earliest_time": earliest_time,
                "latest_time": latest_time,
                "exec_mode": "normal",
            },
        )
        sid = job["sid"]
        state = await self._wait_for_job(sid)
        if state != "DONE":
            return json.dumps({"error": f"Search job ended with state: {state}", "sid": sid})

        results_data = await self._get(
            f"/services/search/jobs/{sid}/results",
            {"count": str(min(max_results, 10_000)), "output_mode": "json"},
        )
        results = results_data.get("results", [])
        fields = [f["name"] for f in results_data.get("fields", [])]
        return json.dumps(
            {"mode": "async", "sid": sid, "result_count": len(results), "fields": fields, "results": results},
            indent=2, default=str,
        )

    async def list_indexes(self) -> str:
        data = await self._get("/services/data/indexes", {"count": "0"})
        indexes = [
            {
                "name": e["name"],
                "total_event_count": e["content"].get("totalEventCount", 0),
                "current_db_size_mb": e["content"].get("currentDBSizeMB", 0),
                "earliest_time": e["content"].get("minTime", ""),
                "latest_time": e["content"].get("maxTime", ""),
                "disabled": e["content"].get("disabled", False),
            }
            for e in data.get("entry", [])
            if not e["content"].get("disabled", False)
        ]
        indexes.sort(key=lambda x: x["name"])
        return json.dumps({"count": len(indexes), "indexes": indexes}, indent=2)

    async def get_index_info(self, index_name: str) -> str:
        data = await self._get(f"/services/data/indexes/{index_name}")
        e = data["entry"][0]
        c = e["content"]
        return json.dumps(
            {
                "name": e["name"],
                "total_event_count": c.get("totalEventCount", 0),
                "current_db_size_mb": c.get("currentDBSizeMB", 0),
                "earliest_time": c.get("minTime", ""),
                "latest_time": c.get("maxTime", ""),
                "retention_days": round(c.get("frozenTimePeriodInSecs", 0) / 86400, 1),
                "home_path": c.get("homePath", ""),
            },
            indent=2,
        )

    async def list_saved_searches(self) -> str:
        data = await self._get("/services/saved/searches", {"count": "0"})
        searches = [
            {
                "name": e["name"],
                "query": e["content"].get("search", ""),
                "description": e["content"].get("description", ""),
                "is_scheduled": bool(e["content"].get("is_scheduled", False)),
                "cron_schedule": e["content"].get("cron_schedule", ""),
            }
            for e in data.get("entry", [])
        ]
        return json.dumps({"count": len(searches), "saved_searches": searches}, indent=2)

    async def run_saved_search(self, search_name: str) -> str:
        dispatch = await self._post(f"/services/saved/searches/{search_name}/dispatch", {})
        sid = dispatch["sid"]
        state = await self._wait_for_job(sid)
        if state != "DONE":
            return json.dumps({"error": f"Job ended with state: {state}", "sid": sid})
        results_data = await self._get(
            f"/services/search/jobs/{sid}/results", {"count": "1000", "output_mode": "json"}
        )
        results = results_data.get("results", [])
        return json.dumps(
            {"search_name": search_name, "sid": sid, "result_count": len(results), "results": results},
            indent=2, default=str,
        )

    async def create_alert(self, name: str, query: str, cron_schedule: str, condition: str, description: str) -> str:
        await self._post(
            "/services/saved/searches",
            {
                "name": name,
                "search": query,
                "description": description,
                "is_scheduled": "1",
                "cron_schedule": cron_schedule,
                "alert_type": "always",
                "alert.severity": "3",
                "alert.suppress": "0",
            },
        )
        return json.dumps(
            {"status": "created", "name": name, "query": query, "cron_schedule": cron_schedule},
            indent=2,
        )

    async def list_alerts(self) -> str:
        data = await self._get("/services/saved/searches", {"count": "0", "search": "is_scheduled=1"})
        alerts = [
            {
                "name": e["name"],
                "query": e["content"].get("search", ""),
                "description": e["content"].get("description", ""),
                "cron_schedule": e["content"].get("cron_schedule", ""),
                "last_fired_time": e["content"].get("alert.last_fired", ""),
                "severity": e["content"].get("alert.severity", "3"),
            }
            for e in data.get("entry", [])
            if e["content"].get("is_scheduled")
        ]
        return json.dumps({"count": len(alerts), "alerts": alerts}, indent=2)

    async def delete_alert(self, name: str) -> str:
        await self._delete(f"/services/saved/searches/{name}")
        return json.dumps({"status": "deleted", "name": name}, indent=2)

    async def list_dashboards(self) -> str:
        data = await self._get("/servicesNS/-/-/data/ui/views", {"count": "0", "search": "isDashboard=1"})
        dashboards = []
        for e in data.get("entry", []):
            c = e["content"]
            # Extract panel search strings from the XML definition
            import re as _re
            xml = c.get("eai:data", "")
            queries = _re.findall(r"<query>([^<]+)</query>", xml)
            dashboards.append({
                "name": e["name"],
                "label": c.get("label", e["name"]),
                "panel_queries": queries,
            })
        return json.dumps({"count": len(dashboards), "dashboards": dashboards}, indent=2)

    async def get_server_info(self) -> str:
        data = await self._get("/services/server/info")
        c = data["entry"][0]["content"]
        mode = await self.get_connection_mode()
        return json.dumps(
            {
                "version": c.get("version", ""),
                "build": c.get("build", ""),
                "product_type": c.get("product_type", ""),
                "server_name": c.get("serverName", ""),
                "os_name": c.get("os_name", ""),
                "connection_mode": mode,
            },
            indent=2,
        )
