"""Probe the Splunk licenser REST API — GET various endpoints to learn the structure."""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

import httpx

HOST     = os.getenv("SPLUNK_HOST")
USERNAME = os.getenv("SPLUNK_USERNAME", "")
PASSWORD = os.getenv("SPLUNK_PASSWORD", "")
BASE     = f"https://{HOST}"


async def web_login(client: httpx.AsyncClient) -> str:
    await client.get(f"{BASE}/en-US/account/login")
    cval = client.cookies.get("cval", "")
    await client.post(f"{BASE}/en-US/account/login", data={
        "username": USERNAME, "password": PASSWORD,
        "set_has_logged_in": "false", "return_to": "/en-US/", "cval": cval,
    })
    await client.get(f"{BASE}/en-US/")
    for k, v in client.cookies.items():
        if k.startswith("splunkweb_csrf_token"):
            return v
    return ""


async def raw_get(client: httpx.AsyncClient, csrf: str, path: str) -> dict:
    url = f"{BASE}/en-US/splunkd/__raw{path}"
    r = await client.get(url, headers={
        "X-Requested-With": "XMLHttpRequest",
        "X-Splunk-Form-Key": csrf,
    }, params={"output_mode": "json", "count": "0"})
    print(f"GET {path}  ->  HTTP {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"  Body: {r.text[:300]}")
    return {}


async def main():
    async with httpx.AsyncClient(verify=True, timeout=30.0, follow_redirects=True) as c:
        print("Logging in ...")
        csrf = await web_login(c)
        print(f"  CSRF token: {csrf[:20]}...")
        print()

        # 1. List licenser groups
        data = await raw_get(c, csrf, "/services/licenser/groups")
        for e in data.get("entry", []):
            print(f"  Group: {e['name']}  stack_id={e['content'].get('stack_id')}  is_active={e['content'].get('is_active')}")
        print()

        # 2. List licenser stacks
        data = await raw_get(c, csrf, "/services/licenser/stacks")
        for e in data.get("entry", []):
            print(f"  Stack: {e['name']}  type={e['content'].get('type')}  quota={e['content'].get('quota')}")
        print()

        # 3. List installed licenses
        data = await raw_get(c, csrf, "/services/licenser/licenses")
        licenses = data.get("entry", [])
        print(f"  {len(licenses)} license(s) installed:")
        for e in licenses:
            c2 = e["content"]
            print(f"    - {e['name']}")
            print(f"        type    : {c2.get('type')}")
            print(f"        label   : {c2.get('label')}")
            print(f"        quota   : {c2.get('quota')}")
            print(f"        expires : {c2.get('expiration_time')}")
            print(f"        status  : {c2.get('status')}")
            print()

        # 4. List licenser slaves/peers
        data2 = await raw_get(c, csrf, "/services/licenser/slaves")
        for e in data2.get("entry", []):
            print(f"  Slave: {e['name']}  active_pool={e['content'].get('active_pool')}")
        print()

        # 5. Check messages/capabilities
        data3 = await raw_get(c, csrf, "/services/licenser/messages")
        msgs = data3.get("entry", [])
        if msgs:
            print(f"  {len(msgs)} licenser message(s):")
            for e in msgs:
                print(f"    - {e['content'].get('description', e['name'])}")
        else:
            print("  No licenser messages.")


if __name__ == "__main__":
    asyncio.run(main())
