"""Debug Splunk web login to find where the CSRF form key lives."""
import asyncio
import os
import re
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

import httpx

HOST = os.getenv("SPLUNK_HOST")
USER = os.getenv("SPLUNK_USERNAME")
PASS = os.getenv("SPLUNK_PASSWORD")
BASE = f"https://{HOST}"


async def probe():
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=True) as c:
        # ── Step 1: GET login page ────────────────────────────────────────────
        r = await c.get(f"{BASE}/en-US/account/login")
        print("=== GET /en-US/account/login ===")
        print(f"  HTTP {r.status_code}")
        print("  Cookies set:")
        for k, v in c.cookies.items():
            print(f"    {k} = {v[:80]}")

        # Try to find cval
        cval = c.cookies.get("cval", "")
        m = re.search(r'name="cval"\s+value="([^"]+)"', r.text)
        if m:
            cval = m.group(1)

        # Look for any form_key variant in HTML
        for pattern_name, pattern in [
            ("form_key",         r'form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
            ("splunk_form_key",  r'splunk_form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
            ("X-Splunk-Form-Key",r'X-Splunk-Form-Key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
        ]:
            m2 = re.search(pattern, r.text, re.IGNORECASE)
            print(f"  {pattern_name} in HTML: {m2.group(1)[:40] if m2 else 'NOT FOUND'}")

        # Print a snippet of HTML around 'form_key' if it appears
        idx = r.text.lower().find("form_key")
        if idx >= 0:
            print(f"  HTML snippet near 'form_key': ...{r.text[max(0,idx-30):idx+80]}...")

        # ── Step 2: POST login ────────────────────────────────────────────────
        print()
        r2 = await c.post(
            f"{BASE}/en-US/account/login",
            data={
                "username": USER,
                "password": PASS,
                "set_has_logged_in": "false",
                "return_to": "/en-US/",
                "cval": cval,
            },
        )
        print(f"=== POST /en-US/account/login  HTTP {r2.status_code} ===")
        print("  Cookies after login:")
        for k, v in c.cookies.items():
            print(f"    {k} = {v[:80]}")

        # Look for form_key in post-login response
        for pattern_name, pattern in [
            ("form_key",         r'form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
            ("splunk_form_key",  r'splunk_form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
        ]:
            m3 = re.search(pattern, r2.text, re.IGNORECASE)
            print(f"  {pattern_name} in login response HTML: {m3.group(1)[:40] if m3 else 'NOT FOUND'}")

        # ── Step 3: GET the home page — often sets the form key ───────────────
        print()
        r3 = await c.get(f"{BASE}/en-US/")
        print(f"=== GET /en-US/  HTTP {r3.status_code} ===")
        print("  Cookies:")
        for k, v in c.cookies.items():
            print(f"    {k} = {v[:80]}")

        for pattern_name, pattern in [
            ("form_key",         r'form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
            ("splunk_form_key",  r'splunk_form_key["\s]*[=:]["\s]*([a-zA-Z0-9_\-]{8,})'),
            ("Backbone.SPLUNKWEB_VERSION_LABEL", r'SPLUNKWEB_VERSION_LABEL.*?([0-9.]+)'),
        ]:
            m4 = re.search(pattern, r3.text, re.IGNORECASE)
            print(f"  {pattern_name} in /en-US/ HTML: {m4.group(1)[:60] if m4 else 'NOT FOUND'}")

        idx2 = r3.text.lower().find("form_key")
        if idx2 >= 0:
            print(f"  HTML snippet near 'form_key': ...{r3.text[max(0,idx2-30):idx2+100]}...")


if __name__ == "__main__":
    asyncio.run(probe())
