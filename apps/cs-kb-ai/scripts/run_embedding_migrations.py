#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import repository  # noqa: E402
from app.embedding_migration_worker import run_pending_embedding_migrations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pending embedding migration jobs in bounded batches.")
    parser.add_argument("--batch-size", type=int, default=100, help="Items to re-embed per migration batch")
    parser.add_argument("--max-batches", type=int, default=10, help="Maximum job batches to run before exiting")
    parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        help="Migration status to include. Repeat to include multiple statuses. Defaults to pending and in_progress.",
    )
    parser.add_argument("--skip-ensure-schema", action="store_true", help="Do not run repository.ensure_schema() first")
    args = parser.parse_args()

    if not args.skip_ensure_schema:
        repository.ensure_schema()

    summary = run_pending_embedding_migrations(
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        statuses=args.statuses,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary.get("stopped_reason") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
