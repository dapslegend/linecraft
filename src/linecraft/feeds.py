"""Pull upcoming games from Sporty, 1xBet, or a generic JSON feed.

This module only reads public lines. It does not place a stake.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class FeedError(RuntimeError):
    pass


def _get(url: str, timeout: int = 40) -> Any:
    if not url:
        raise FeedError("feed URL is empty")
    origin = os.environ.get("SPORTY_ORIGIN", "https://www.sportybet.com")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": origin,
            "Referer": origin + "/ng/",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise FeedError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise FeedError(f"network error for {url}: {exc.reason}") from exc


def sporty_urls() -> dict[str, str]:
    origin = os.environ.get("SPORTY_ORIGIN", "https://www.sportybet.com").rstrip("/")
    return {
        "upcoming": os.environ.get(
            "SPORTY_UPCOMING_URL", origin + "/api/ng/factsCenter/pcUpcomingEvents"
        ),
        "event": os.environ.get("SPORTY_EVENT_URL", origin + "/api/ng/factsCenter/event"),
        "sports": os.environ.get("SPORTY_SPORTS_URL", origin + "/api/ng/factsCenter/sportList"),
        "share": os.environ.get("SPORTY_SHARE_URL", origin + "/api/ng/orders/share"),
    }


def pull_sporty(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull every configured sport page. Returns normalised fixtures, not bets."""
    urls = sporty_urls()
    sports_payload = _get(urls["sports"])
    listed = {
        str(row.get("name") or ""): str(row.get("id") or "")
        for row in (sports_payload.get("data") or [])
        if isinstance(row, dict)
    }
    pages = config.get("pages") or {}
    markets = config.get("markets") or {}
    fixtures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sport in config.get("sports") or []:
        sid = listed.get(str(sport))
        if not sid:
            continue
        for market_id in markets.get(sport) or ["1"]:
            page_count = int(pages.get(sport) or 1)
            for page in range(1, page_count + 1):
                url = (
                    f"{urls['upcoming']}?sportId={sid}&marketId={market_id}"
                    f"&pageSize=100&pageNum={page}"
                )
                payload = _get(url)
                tours = ((payload.get("data") or {}).get("tournaments") or [])
                if not tours:
                    break
                for tour in tours:
                    if not isinstance(tour, dict):
                        continue
                    for event in tour.get("events") or []:
                        if not isinstance(event, dict):
                            continue
                        event_id = str(event.get("eventId") or "")
                        if not event_id or event_id in seen:
                            continue
                        seen.add(event_id)
                        fixtures.append(
                            {
                                "provider": "sporty",
                                "eventId": event_id,
                                "sport": sport,
                                "home": str(event.get("homeTeamName") or ""),
                                "away": str(event.get("awayTeamName") or ""),
                                "tournament": str(tour.get("name") or ""),
                                "startMs": int(event.get("estimateStartTime") or 0),
                                "marketId": str(market_id),
                                "markets": event.get("markets") or [],
                            }
                        )
    return fixtures


def pull_1xbet(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the 1xBet line feed. Share is refused unless ONEXBET_SHARE_URL is set."""
    url = os.environ.get("ONEXBET_LINE_URL", "")
    if not url:
        raise FeedError("ONEXBET_LINE_URL is empty")
    sports = {name.casefold() for name in (config.get("sports") or [])}
    payload = _get(url)
    rows = payload.get("Value") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise FeedError("1xbet feed did not return a list")
    fixtures = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sport = str(row.get("SN") or row.get("sport") or "")
        if sports and sport.casefold() not in sports and sport:
            continue
        event_id = str(row.get("CI") or row.get("I") or row.get("id") or "")
        if not event_id:
            continue
        fixtures.append(
            {
                "provider": "1xbet",
                "eventId": event_id,
                "sport": sport or "Unknown",
                "home": str(row.get("O1") or row.get("home") or ""),
                "away": str(row.get("O2") or row.get("away") or ""),
                "tournament": str(row.get("L") or row.get("league") or ""),
                "startMs": int(row.get("S") or row.get("start") or 0) * (1000 if int(row.get("S") or 0) < 10_000_000_000 else 1),
                "marketId": "1",
                "markets": row.get("E") or row.get("markets") or [],
            }
        )
    return fixtures


def pull_generic(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull a caller-mapped JSON feed. Expects a list of event objects."""
    url = os.environ.get("GENERIC_EVENTS_URL", "")
    payload = _get(url)
    rows = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise FeedError("generic feed must be a list or an object with events")
    fixtures = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("eventId"):
            continue
        fixtures.append(
            {
                "provider": "generic",
                "eventId": str(row.get("eventId")),
                "sport": str(row.get("sport") or "Unknown"),
                "home": str(row.get("home") or ""),
                "away": str(row.get("away") or ""),
                "tournament": str(row.get("tournament") or ""),
                "startMs": int(row.get("startMs") or 0),
                "marketId": str(row.get("marketId") or "1"),
                "markets": row.get("markets") or [],
            }
        )
    return fixtures


def pull_games(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull all games for the provider named in config. Default is sporty."""
    provider = str(config.get("provider") or os.environ.get("LINECRAFT_PROVIDER") or "sporty").casefold()
    if provider in {"sporty", "sportybet"}:
        return pull_sporty(config)
    if provider in {"1xbet", "onexbet", "1x"}:
        return pull_1xbet(config)
    if provider in {"generic", "any", "custom"}:
        return pull_generic(config)
    raise FeedError(f"unknown provider: {provider}")
