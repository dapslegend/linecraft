"""Pull the configured book, research with Grok, and share. Never stake."""

from __future__ import annotations

import argparse
import json
import sys

from linecraft.book import BookError, assert_share_only, book_share
from linecraft.config import load_config
from linecraft.feeds import FeedError, pull_games
from linecraft.grok import GrokError, think


def selections_from_keeps(keeps: list[dict]) -> list[dict]:
    """A share needs a grid outcome id. Research text alone is not enough."""
    ready = []
    for row in keeps:
        if not row.get("eventId") or not row.get("outcomeId") or not row.get("marketId"):
            continue
        ready.append(row)
    return ready


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Linecraft share-only booker. Does not stake.")
    parser.add_argument("--config", default="", help="Path to config JSON. Defaults from LINECRAFT_CONFIG.")
    parser.add_argument("--pull-only", action="store_true", help="Print the fixture board and do not call Grok or share.")
    parser.add_argument("--no-book", action="store_true", help="Research, but do not post a share code.")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config or None)
        assert_share_only(config)
    except (OSError, ValueError, json.JSONDecodeError, BookError) as exc:
        print(f"CONFIG_FAIL {exc}", file=sys.stderr)
        return 2
    try:
        board = pull_games(config)
    except FeedError as exc:
        print(f"FEED_FAIL {exc}", file=sys.stderr)
        return 3
    board = board[: int(config.get("max_board") or 24)]
    print(f"BOARD {len(board)} provider={config.get('provider')}", flush=True)
    if args.pull_only:
        print(json.dumps(board, indent=2))
        return 0
    try:
        keeps = think(board, config)
    except (GrokError, json.JSONDecodeError) as exc:
        print(f"GROK_FAIL {exc}", file=sys.stderr)
        return 4
    print(f"KEEPS {len(keeps)}", flush=True)
    ready = selections_from_keeps(keeps)
    if args.no_book or not ready:
        print(json.dumps({"keeps": keeps, "booked": False, "stake": False}, indent=2))
        return 0
    try:
        result = book_share(config, ready)
    except BookError as exc:
        print(f"BOOK_FAIL {exc}", file=sys.stderr)
        return 5
    code = ((result.get("data") or {}).get("shareCode") or result.get("shareCode"))
    print(json.dumps({
        "shareCode": code,
        "bizCode": result.get("bizCode"),
        "n": len(ready),
        "stake": False,
        "notSure": True,
    }, indent=2))
    return 0 if code else 5


if __name__ == "__main__":
    raise SystemExit(main())
