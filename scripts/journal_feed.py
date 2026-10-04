#!/usr/bin/env python3
"""Run the read-only AICFA persistent journal HTTP feed."""
from __future__ import annotations

import argparse
import os

from aicfa.journal_feed import serve_journal
from aicfa.persistent_journal import PersistentJournal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("AICFA_JOURNAL_FEED_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AICFA_JOURNAL_FEED_PORT", "8090")),
    )
    args = parser.parse_args()

    journal = PersistentJournal.from_env()
    if journal is None:
        raise SystemExit("AICFA_DATA_DIR or AICFA_JOURNAL_PATH must be configured")

    serve_journal(journal, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
