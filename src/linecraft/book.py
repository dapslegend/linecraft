"""Share-code booking. Never stakes.

A share posts a selection list and returns a code. It does not set a stake,
does not accept a bet, and does not move money.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from linecraft.feeds import sporty_urls

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class BookError(RuntimeError):
    pass


def assert_share_only(config: dict[str, Any]) -> None:
    book = config.get("book") or {}
    if book.get("stake") is not False or book.get("mode") not in (None, "share"):
        raise BookError("refusing to run: book.stake must be false and book.mode must be share")
    if not book.get("enabled", True):
        raise BookError("booking is disabled in config")


def share_sporty(selections: list[dict[str, Any]]) -> dict[str, Any]:
    """Post a Sporty share. Odds must be strings. No stake field is sent."""
    url = sporty_urls()["share"]
    origin = os.environ.get("SPORTY_ORIGIN", "https://www.sportybet.com")
    body = {
        "selections": [
            {
                "eventId": row["eventId"],
                "marketId": str(row["marketId"]),
                "specifier": str(row.get("specifier") or ""),
                "outcomeId": str(row["outcomeId"]),
                "odds": f"{float(row['odds']):.2f}",
            }
            for row in selections
        ]
    }
    if any("stake" in row for row in body["selections"]):
        raise BookError("selection payload must not contain a stake")
    if any(not isinstance(row["odds"], str) for row in body["selections"]):
        raise BookError("share odds must be strings")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": origin,
            "Referer": origin + "/ng/",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise BookError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BookError(f"network error: {exc.reason}") from exc
    return payload


def book_share(config: dict[str, Any], selections: list[dict[str, Any]]) -> dict[str, Any]:
    """Book a share code for the configured provider. Never stakes."""
    assert_share_only(config)
    if not selections:
        raise BookError("nothing to book")
    provider = str(config.get("provider") or "sporty").casefold()
    if provider in {"sporty", "sportybet"}:
        return share_sporty(selections)
    if provider in {"1xbet", "onexbet", "1x"}:
        url = os.environ.get("ONEXBET_SHARE_URL", "")
    else:
        url = os.environ.get("GENERIC_SHARE_URL", "")
    if not url:
        raise BookError(f"{provider} has no share URL; pull is allowed, booking is refused")
    raise BookError(f"{provider} share route is not implemented; refusing rather than staking")
