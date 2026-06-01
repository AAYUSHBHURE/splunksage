"""Try various ways to use JWT token through port 443."""
import asyncio, httpx, os, sys
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

HOST  = os.getenv("SPLUNK_HOST")
TOKEN = os.getenv("SPLUNK_TOKEN")
TARGET = f"https://{HOST}/en-US/splunkd/__raw/services/server/info?output_mode=json"

# Cookie names Splunk Cloud may accept for JWT token auth
COOKIE_ATTEMPTS = [
    {"splunkd_8089": TOKEN},
    {"splunk_jwt": TOKEN},
    {"token": TOKEN},
    {"splunkwebui_csrf": TOKEN},
    {"Authorization": TOKEN},
]

async def probe():
    print(f"Target: {TARGET}\n")

    # 1. Try each cookie variation
    async with httpx.AsyncClient(verify=True, timeout=10.0, follow_redirects=False) as c:
        for cookies in COOKIE_ATTEMPTS:
            r = await c.get(TARGET, cookies=cookies)
            cookie_str = list(cookies.keys())[0]
            if r.status_code == 200:
                print(f"[SUCCESS] Cookie '{cookie_str}' worked! Status 200")
                print(r.text[:300])
                return
            else:
                loc = r.headers.get("location", "")[:80]
                print(f"[{r.status_code}] Cookie '{cookie_str}' -> {loc or r.text[:80]!r}")

    # 2. Try token in X-Splunk-Form-Key header (CSRF bypass attempt)
    async with httpx.AsyncClient(verify=True, timeout=10.0, follow_redirects=False) as c:
        r = await c.get(TARGET, headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Requested-With": "XMLHttpRequest",
            "X-Splunk-Form-Key": TOKEN[:20],
        })
        print(f"\n[{r.status_code}] XHR + Bearer header -> {r.text[:120]!r}")

    print("\n--- Session login approach needed ---")
    print("The JWT token only works on port 8089 (direct REST API).")
    print("To use port 443, we need username + password for session auth.")
    print("Please provide your current Splunk password (the one you set after login).")

asyncio.run(probe())
