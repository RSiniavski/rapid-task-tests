"""Download the two CDN scripts used by board.html / dashboard.html into vendor/ so the browser
tests run offline and deterministically (the Playwright context serves them instead of the CDN).

Usage:  python tools/fetch_vendor.py
"""
import sys
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor"
FILES = {
    "vue.global.prod.js": "https://unpkg.com/vue@3.4.21/dist/vue.global.prod.js",
    "Sortable.min.js": "https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js",
}

if __name__ == "__main__":
    VENDOR.mkdir(exist_ok=True)
    for name, url in FILES.items():
        dest = VENDOR / name
        print(f"GET {url}")
        try:
            data = urllib.request.urlopen(url, timeout=30).read()  # noqa: S310
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            sys.exit(1)
        dest.write_bytes(data)
        print(f"  -> {dest} ({len(data)} bytes)")
