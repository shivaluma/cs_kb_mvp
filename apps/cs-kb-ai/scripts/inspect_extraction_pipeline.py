#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect extraction pipeline output for a document version via the CS KB API.")
    parser.add_argument("version_id", help="Document version UUID to inspect")
    parser.add_argument("--base-url", default="http://localhost:8000", help="AI service base URL, default: http://localhost:8000")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of the readable markdown report")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    suffix = "inspection" if args.json else "inspection.md"
    url = f"{base_url}/ai/v1/versions/{args.version_id}/extraction-pipeline/{suffix}"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json" if args.json else "text/plain"}), timeout=15) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"API returned HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Could not reach {url}: {exc.reason}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
