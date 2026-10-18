"""Pull the configured book, research with Grok, and share. Never stake."""

from __future__ import annotations

import argparse
import json
import sys

from linecraft.book import BookError, assert_share_only, book_share
from linecraft.config import load_config
from linecraft.feeds import FeedError, pull_games
from linecraft.grok import GrokError, think


def _side(desc: str) -> str:
    text = (desc or "").strip().lower()
    for token in ("over", "under", "home", "away", "draw"):
        if text == token or text.startswith(token + " "):
            return token
    return text


def _line(spec: str):
    try:
        return float(str(spec).split("=", 1)[1])
    except (IndexError, ValueError):
        return None


def match_keep(keep: dict, fixture: dict) -> dict | None:
    """Copy the live grid outcome. A text pick with no outcome id is not booked."""
    want = _side(str(keep.get("selection") or ""))
    if not want:
        return None
    want_line = _line(str(keep.get("specifier") or ""))
    if want_line is None:
        found = __import__("re").search(r"(\d+\.5)", str(keep.get("selection") or ""))
        want_line = float(found.group(1)) if found else None
    for market in fixture.get("markets") or []:
        if not isinstance(market, dict):
            continue
        mid = str(market.get("id") or market.get("marketId") or fixture.get("marketId") or "")
        spec = str(market.get("specifier") or "")
        line = _line(spec)
        if want_line is not None and line is not None and abs(line - want_line) > 0.01:
            continue
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            if _side(str(outcome.get("desc") or outcome.get("name") or "")) != want:
                continue
            oid = outcome.get("id") or outcome.get("outcomeId")
            if not oid or not mid:
                continue
            try:
                odds = float(outcome.get("odds"))
            except (TypeError, ValueError):
                continue
            return {
                "eventId": fixture.get("eventId"),
                "marketId": mid,
                "specifier": spec,
                "outcomeId": str(oid),
                "odds": f"{odds:.2f}",
            }
    if keep.get("eventId") and keep.get("outcomeId") and keep.get("marketId") and keep.get("odds"):
        return {
            "eventId": keep["eventId"],
            "marketId": str(keep["marketId"]),
            "specifier": str(keep.get("specifier") or ""),
            "outcomeId": str(keep["outcomeId"]),
            "odds": f"{float(keep['odds']):.2f}",
        }
    return None


def selections_from_keeps(keeps: list[dict], fixtures: list[dict] | None = None) -> list[dict]:
    """A share needs a grid outcome id. Research text alone is not enough."""
    by_id = {str(row.get("eventId")): row for row in (fixtures or []) if row.get("eventId")}
    ready = []
    seen = set()
    for row in keeps:
        event_id = str(row.get("eventId") or "")
        if not event_id or event_id in seen:
            continue
        matched = match_keep(row, by_id.get(event_id) or {"eventId": event_id, "markets": []})
        if matched is None:
            continue
        seen.add(event_id)
        ready.append(matched)
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
    cap = int(config.get("max_legs") or 50)
    ready = selections_from_keeps(keeps, board)[:cap]
    if args.no_book or not ready:
        print(json.dumps({"keeps": keeps, "booked": False, "stake": False}, indent=2))
        return 0
    try:
        result = book_share(config, ready)
    except BookError as exc:
        print(f"BOOK_FAIL {exc}", file=sys.stderr)
        return 5
    code = ((result.get("data") or {}).get("shareCode") or result.get("shareCode"))
    ok = str(result.get("bizCode")) == "10000" and bool(code)
    print(json.dumps({
        "shareCode": code if ok else None,
        "bizCode": result.get("bizCode"),
        "message": result.get("message"),
        "n": len(ready),
        "stake": False,
        "notSure": True,
    }, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
