"""Grok research. A keep without a sourced fact is discarded.

The model is asked to think and search. This module never places a stake.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

FACT_RE = re.compile(
    r"(\d|injur|suspend|goalie|starter|line-?up|last \d|won \d|lost \d|table|ranked)",
    re.I,
)
BOTH_TEAMS_RE = re.compile(
    r"\b(both|each|neither)\b.{0,40}\b(team|side|club)s?\b|"
    r"\b(home|hosts?).{0,50}\b(away|visitors|guests)\b|"
    r"\b(away|visitors|guests).{0,50}\b(home|hosts?)\b",
    re.I,
)
LOW_SCORE_RE = re.compile(
    r"(low[- ]scor|few goals|shut ?out|clean sheet|scored (only |just )?(0|1|2)\b|"
    r"failed to score|goalless|gpg|goals per game|conceded (only |just )?(0|1|2)\b|"
    r"good defen[cs]|weak attack|bad attack|striker (out|injured|suspended))",
    re.I,
)
def _rates(text: str) -> list[float]:
    blob = text or ""
    rates = [float(m) for m in re.findall(r"(\d+\.\d+|\d+)\s*(?:gpg|goals? per game|ppg|points per game)", blob, re.I)]
    rates += [float(m) for m in re.findall(r"(?:average|avg|averaging)\s*(\d+\.\d+|\d+)", blob, re.I)]
    return rates


def _line_from(text: str):
    found = re.search(r"\b(?:over|under)\s*(\d+\.5)\b", text or "", re.I)
    return float(found.group(1)) if found else None


class GrokError(RuntimeError):
    pass


def grok_settings(config: dict[str, Any]) -> dict[str, Any]:
    grok = dict(config.get("grok") or {})
    grok["enabled"] = bool(grok.get("enabled", True))
    grok["model"] = os.environ.get("GROK_MODEL") or grok.get("model") or "grok-4.7"
    grok["timeout_seconds"] = int(grok.get("timeout_seconds") or 240)
    grok["require_search"] = bool(grok.get("require_search", True))
    grok["api_key"] = os.environ.get("GROK_API_KEY") or ""
    base = os.environ.get("GROK_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    grok["url"] = base + "/responses"
    return grok


def search_count(body: dict[str, Any]) -> int:
    count = 0
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "")
        name = str(item.get("name") or "")
        if kind in {"web_search_call", "x_search_call"} or "search" in name:
            count += 1
    usage = body.get("usage") or {}
    return max(count, int(usage.get("num_server_side_tools_used") or 0))


def output_text(body: dict[str, Any]) -> str:
    chunks = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"message", "output_message"}:
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    chunks.append(str(part.get("text") or ""))
        if item.get("type") == "output_text" and item.get("text"):
            chunks.append(str(item.get("text")))
    return "\n".join(chunks) or str(body.get("output_text") or "")


def side_of(desc: str) -> str:
    text = (desc or "").strip().lower()
    for token in ("over", "under", "home", "away", "draw"):
        if text == token or text.startswith(token + " "):
            return token
    return text


def under_is_strict(text: str) -> bool:
    blob = (text or "").strip()
    if len(blob) < 40 or not FACT_RE.search(blob):
        return False
    if re.search(r"\b(not confirmed|not checked|unconfirmed|unknown|no data)\b", blob, re.I):
        return False
    return bool(BOTH_TEAMS_RE.search(blob) and LOW_SCORE_RE.search(blob))


XG_BAND = 1.43


def _xg_pair(text: str):
    blob = text or ""
    home = away = None

    def _take(label, value):
        nonlocal home, away
        if label == "home" and home is None:
            home = value
        elif label == "away" and away is None:
            away = value

    for match in re.finditer(
        r"\b(home|hosts?|away|visitors|guests)\b[^.]{0,80}?"
        r"(\d+\.\d+|\d+)\s*(?:gpg|goals? per game|xg|expected goals)",
        blob,
        re.I,
    ):
        label = "home" if match.group(1).lower().startswith("h") else "away"
        _take(label, float(match.group(2)))
    for match in re.finditer(
        r"\b(home|hosts?|away|visitors|guests)\b[^.]{0,40}?"
        r"(?:average|avg|averaging|xg)\s*(\d+\.\d+|\d+)",
        blob,
        re.I,
    ):
        label = "home" if match.group(1).lower().startswith("h") else "away"
        _take(label, float(match.group(2)))
    if home is None or away is None or min(home, away) <= 0:
        return None
    return home, away


def result_call(text: str, selection: str):
    """Home/Away only at a 2x expected-goals gap. A 1.43 band is draw or skip."""
    side = side_of(selection)
    if side not in {"home", "away", "draw"}:
        return side
    pair = _xg_pair(text)
    if pair is None:
        return "skip"
    home_xg, away_xg = pair
    if away_xg >= 2 * home_xg:
        return "away"
    if home_xg >= 2 * away_xg:
        return "home"
    if max(home_xg, away_xg) / min(home_xg, away_xg) <= XG_BAND:
        return "draw" if side == "draw" else "skip"
    return "skip"


def over_is_strict(text: str, selection: str = "") -> bool:
    """Over only if both teams' sourced rates clear that line."""
    blob = f"{selection} {text}".strip()
    if len(blob) < 40 or not FACT_RE.search(blob):
        return False
    if re.search(r"\b(not confirmed|not checked|unconfirmed|unknown|no data)\b", blob, re.I):
        return False
    line = _line_from(blob)
    rates = _rates(blob)
    if line is not None and len(rates) >= 2 and (rates[0] + rates[1] > line or min(rates[0], rates[1]) >= line / 2):
        return True
    if line is not None and len(rates) == 1 and rates[0] > line and BOTH_TEAMS_RE.search(blob):
        return True
    return False


def think(fixtures: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask Grok to keep or drop each fixture. No search or no fact means drop."""
    settings = grok_settings(config)
    if not settings["enabled"]:
        return []
    if not settings["api_key"]:
        raise GrokError("GROK_API_KEY is empty")
    if not fixtures:
        return []
    system = (
        "You are a sports analyst. Think before you pick. "
        "Call web_search at least once per match. Use x_search for injury or lineup news. "
        "Do not invent a stat. If you cannot source a concrete fact, selection must be null. "
        "Pick at most one outcome copied from that match grid. "
        "UNDER is banned unless both teams are confirmed very low scoring, well defended, or weak in attack. "
        "OVER is the same standard in reverse. Over 2.5 needs both teams at a combined rate above 2.5, "
        "or each team around 1.5 goals per game. One high-scoring team or a head-to-head note is not enough. "
        "If neither test is sourced, selection must be null. "
        "For football Home, Draw, or Away, write home xG and away xG. "
        "Away only if away xG is at least twice home xG. Home only if home xG is at least twice away xG. "
        "A ratio inside 1.43 is Draw or null. Home advantage is not a substitute. "
        "Never say sure, lock, 80%, or 100. This is research for a share code, not a stake. "
        'Final message is JSON only: {"picks":[{"eventId":"","selection":null,"marketId":"","outcomeId":"","specifier":"","odds":null,'
        '"fact":"one sourced fact with a number, injury, or lineup"}]}'
    )
    blocks = []
    for row in fixtures:
        prices = row.get("markets") or []
        blocks.append(
            f"MATCH eventId={row.get('eventId')} {row.get('home')} vs {row.get('away')} "
            f"sport={row.get('sport')} league={row.get('tournament')} grid={json.dumps(prices)[:500]}"
        )
    payload = {
        "model": settings["model"],
        "temperature": 0.2,
        "max_output_tokens": 1800,
        "tools": [{"type": "web_search"}, {"type": "x_search"}],
        "tool_choice": "auto",
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Research every match. Then pick or null.\n\n" + "\n".join(blocks)},
        ],
    }
    req = urllib.request.Request(
        settings["url"],
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
            "User-Agent": "linecraft-grok/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings["timeout_seconds"]) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:180]
        raise GrokError(f"HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise GrokError(f"network error: {exc.reason}") from exc
    if settings["require_search"] and search_count(body) < 1:
        return []
    text = output_text(body)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return []
    parsed = json.loads(match.group(0))
    rows = parsed.get("picks") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        return []
    kept = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("selection"):
            continue
        fact = str(row.get("fact") or "")
        if len(fact) < 40 or not FACT_RE.search(fact):
            continue
        side = side_of(str(row.get("selection") or ""))
        if side == "under" and not under_is_strict(fact):
            continue
        if side == "over" and not over_is_strict(fact, str(row.get("selection") or "")):
            continue
        if side in {"home", "away", "draw"}:
            call = result_call(fact, side)
            if call == "skip" or call != side:
                continue
        kept.append(
            {
                "eventId": str(row.get("eventId") or ""),
                "selection": str(row.get("selection")),
                "marketId": str(row.get("marketId") or ""),
                "outcomeId": str(row.get("outcomeId") or ""),
                "specifier": str(row.get("specifier") or ""),
                "odds": row.get("odds"),
                "fact": fact[:180],
            }
        )
    return kept
