"""
Install a Splunk license via the REST API.

Reference: POST /services/licenser/licenses
  payload = full XML license text

Handles Splunk Cloud web-session auth:
  - CSRF token is in cookie  splunkweb_csrf_token_<port>
  - Sent as header           X-Splunk-Form-Key: <value>
"""

import asyncio
import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

import httpx

LICENSE_FILE = Path(r"C:\Users\bhure\Downloads\Splunk.License")

HOST     = os.getenv("SPLUNK_HOST")
USERNAME = os.getenv("SPLUNK_USERNAME", "")
PASSWORD = os.getenv("SPLUNK_PASSWORD", "")
BASE     = f"https://{HOST}"


async def web_login(client: httpx.AsyncClient) -> str:
    """Login via Splunk Web. Returns the CSRF token value."""
    login_url = f"{BASE}/en-US/account/login"

    # GET login page — sets cval + splunkweb_uid cookies
    await client.get(login_url)
    cval = client.cookies.get("cval", "")

    # POST credentials
    await client.post(login_url, data={
        "username": USERNAME,
        "password": PASSWORD,
        "set_has_logged_in": "false",
        "return_to": "/en-US/",
        "cval": cval,
    })

    # Trigger home page to ensure all session cookies are set
    await client.get(f"{BASE}/en-US/")

    # Find the CSRF token cookie — Splunk Cloud names it splunkweb_csrf_token_<port>
    csrf_token = ""
    for k, v in client.cookies.items():
        if k.startswith("splunkweb_csrf_token"):
            csrf_token = v
            print(f"  Found CSRF cookie: {k} = {v[:30]}...")
            break

    if not csrf_token:
        print("  WARNING: No splunkweb_csrf_token cookie found — POST may be rejected")

    return csrf_token


async def main() -> None:
    xml_text = LICENSE_FILE.read_text(encoding="utf-8").strip()
    print(f"License file : {LICENSE_FILE}")
    print(f"Target       : {BASE}")
    print()

    # Parse and echo key fields
    root = ET.fromstring(xml_text)

    def ns(tag: str) -> str:
        node = root.find(f"./payload/{tag}")
        return node.text if node is not None else "?"

    quota_raw = ns("quota")
    quota_gb  = int(quota_raw) // (1024 ** 3) if quota_raw != "?" else "?"
    exp_ts    = int(ns("expiration_time")) if ns("expiration_time") != "?" else 0
    exp_dt    = datetime.datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d") if exp_ts else "?"

    print("  License details:")
    print(f"    Label     : {ns('label')}")
    print(f"    Quota     : {quota_gb} GB/day")
    print(f"    Sub-group : {ns('subgroup_id')}")
    print(f"    GUID      : {ns('guid')}")
    print(f"    Expires   : {exp_dt}")
    print()

    async with httpx.AsyncClient(verify=True, timeout=30.0, follow_redirects=True) as client:

        print("Step 1: Web login ...")
        csrf_token = await web_login(client)
        if "splunkweb_uid" not in client.cookies:
            print("  ERROR: Login failed — splunkweb_uid cookie not set")
            sys.exit(1)
        print(f"  Logged in as {USERNAME}")
        print()

        print("Step 2: POST /services/licenser/licenses ...")
        url = f"{BASE}/en-US/splunkd/__raw/services/licenser/licenses"

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "X-Splunk-Form-Key": csrf_token,
        }
        data = {
            "output_mode": "json",
            "payload": xml_text,
        }

        resp = await client.post(url, headers=headers, data=data)
        print(f"  HTTP {resp.status_code}")

        if resp.status_code in (200, 201):
            try:
                body = resp.json()
                entries = body.get("entry", [])
                if entries:
                    content = entries[0].get("content", {})
                    print()
                    print("SUCCESS - License installed!")
                    print(f"  GUID    : {content.get('guid', '?')}")
                    print(f"  Type    : {content.get('type', '?')}")
                    print(f"  Quota   : {content.get('quota', '?')} bytes")
                    print(f"  Expires : {content.get('expiration_time', '?')}")
                else:
                    print()
                    print("SUCCESS - License POST accepted.")
                    print(json.dumps(body, indent=2)[:800])
            except Exception:
                print("SUCCESS - Response body:")
                print(resp.text[:800])

        else:
            try:
                body = resp.json()
                messages = body.get("messages", [])
                msg = "; ".join(m.get("text", "") for m in messages) or resp.text[:400]
            except Exception:
                msg = resp.text[:400]

            if "already exists" in msg.lower() or "duplicate" in msg.lower():
                print()
                print("NOTE: This license is already installed on this instance.")
                print(f"  {msg}")
            else:
                print()
                print(f"FAILED  HTTP {resp.status_code}")
                print(f"  {msg}")
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
