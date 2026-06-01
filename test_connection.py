"""Live connectivity test — tries sc_admin with both known passwords."""
import asyncio
import json
import os
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

from splunk_mcp_bridge.splunk_client import SplunkClient, SplunkError

HOST  = os.getenv("SPLUNK_HOST")
PORT  = int(os.getenv("SPLUNK_PORT", 8089))
TOKEN = os.getenv("SPLUNK_TOKEN", "")

CANDIDATES = [
    ("sc_admin", "HyperNova@1978"),
    ("sc_admin", "qv7lx01yv6bp0l1i"),   # original temp password
]


async def try_creds(username, password):
    client = SplunkClient(
        host=HOST, port=PORT,
        token=TOKEN, username=username, password=password,
        verify_ssl=True, timeout=20,
    )
    info = json.loads(await client.get_server_info())
    return client, info


async def main():
    print(f"Target: https://{HOST}\n")

    for username, password in CANDIDATES:
        masked = password[:3] + "*" * (len(password) - 3)
        print(f"Trying  sc_admin / {masked} ...")
        try:
            client, info = await try_creds(username, password)
            mode = info.get("connection_mode", "?")
            print(f"\nSUCCESS  (mode: {mode})")
            print(f"  Splunk version : {info.get('version')}")
            print(f"  Product        : {info.get('product_type')}")
            print(f"  Server name    : {info.get('server_name')}")

            print("\nFetching indexes ...")
            idx = json.loads(await client.list_indexes())
            print(f"  Found {idx['count']} index(es):")
            for i in idx["indexes"][:15]:
                print(f"    - {i['name']}  ({i['total_event_count']:,} events, {i['current_db_size_mb']} MB)")
            return

        except SplunkError as e:
            print(f"  FAILED: {e}")
        except Exception as e:
            print(f"  ERROR : {type(e).__name__}: {e}")

    print("\nAll credential combinations failed.")
    print("Please confirm: did you change the temp password when you first logged in?")
    print("If yes, provide the new password. If no, the temp password should still work.")


if __name__ == "__main__":
    asyncio.run(main())
