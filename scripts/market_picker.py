#!/usr/bin/env python3
"""Read-only market-family screener, copied from the weekend research folder.

The original ranked a live bookmaker payload and could be pointed at a share
booker. This copy ranks a payload you already have. It does not fetch, book,
or stake.

    python3 scripts/market_picker.py --self-test
    python3 scripts/market_picker.py --file event.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

from odds_signal import proportional_devig, shin_devig

FAMILIES = {
    "1": "match_result",
    "10": "double_chance",
    "11": "draw_no_bet",
    "18": "match_goals",
    "19": "home_team_goals",
    "20": "away_team_goals",
    "29": "both_teams_score",
    "16": "asian_handicap",
    "166": "corners",
}

EXPECTED_OUTCOMES = {
    "1": 3,
    "10": 3,
    "11": 2,
    "18": 2,
    "19": 2,
    "20": 2,
    "29": 2,
    "16": 2,
    "166": 2,
}

# Lower is better. Result markets are a cleaner simplex than totals.
FAMILY_PRIOR = {
    "match_result": 0,
    "draw_no_bet": 1,
    "double_chance": 2,
    "both_teams_score": 3,
    "match_goals": 4,
    "home_team_goals": 5,
    "away_team_goals": 6,
    "asian_handicap": 7,
    "corners": 8,
}

LIVE_STATUSES = {"ended", "h1", "h2", "ht", "live", "overtime", "penalties"}


@dataclass(frozen=True)
class MarketCandidate:
    event_id: str
    home: str
    away: str
    family: str
    market_id: str
    market_name: str
    specifier: str
    outcome_id: str
    selection: str
    odds: float
    market_probability: float
    shin_probability: float
    overround: float
    margin: float
    hold: float
    shin_z: float


def _is_pre_match(event: dict[str, Any]) -> bool:
    match_status = str(event.get("matchStatus") or "").strip().lower()
    status = str(event.get("status") if event.get("status") is not None else "").strip()
    return match_status not in LIVE_STATUSES and status not in {"1", "2", "3", "4"}


def _active_outcomes(market: dict[str, Any]) -> list[tuple[str, str, float]]:
    rows = []
    for outcome in market.get("outcomes") or []:
        if outcome.get("isActive") not in (1, "1", True, None):
            continue
        try:
            odds = float(outcome.get("odds"))
        except (TypeError, ValueError):
            continue
        if not 1.01 < odds <= 1000:
            continue
        rows.append((str(outcome.get("id") or ""), str(outcome.get("desc") or outcome.get("name") or ""), odds))
    return rows


def rank_market_candidates(event: dict[str, Any], max_hold: float = 0.15) -> list[MarketCandidate]:
    """Return complete supported-market outcomes in screen order.

    Market probability is proportional de-vig of this market alone. It is
    deliberately named to avoid presenting it as a calibrated true chance.
    A low hold improves price quality; it does not prove that a selection is
    mispriced or profitable.
    """
    if not _is_pre_match(event):
        return []

    event_id = str(event.get("eventId") or "")
    home = str(event.get("homeTeamName") or "")
    away = str(event.get("awayTeamName") or "")
    if not event_id or not home or not away:
        return []

    candidates: list[MarketCandidate] = []
    for market in event.get("markets") or []:
        market_id = str(market.get("id") or market.get("marketId") or "")
        family = FAMILIES.get(market_id)
        if family is None or market.get("status") not in (0, "0", None):
            continue
        outcomes = _active_outcomes(market)
        if len(outcomes) != EXPECTED_OUTCOMES[market_id]:
            continue
        raw = [1.0 / odds for _, _, odds in outcomes]
        overround = sum(raw)
        if not 1.0 < overround <= 1.8:
            continue
        # hold is the fraction of stake the overround retains.
        # margin is the raw extra probability mass, overround - 1.
        hold = 1.0 - 1.0 / overround
        margin = overround - 1.0
        if hold > max_hold:
            continue
        fair = proportional_devig(raw)
        shin_fair, shin_z = shin_devig(raw)
        for (outcome_id, selection, odds), probability, shin_probability in zip(outcomes, fair, shin_fair):
            candidates.append(
                MarketCandidate(
                    event_id=event_id,
                    home=home,
                    away=away,
                    family=family,
                    market_id=market_id,
                    market_name=str(market.get("desc") or market.get("name") or family),
                    specifier=str(market.get("specifier") or ""),
                    outcome_id=outcome_id,
                    selection=selection,
                    odds=odds,
                    market_probability=probability,
                    shin_probability=shin_probability,
                    overround=overround,
                    margin=margin,
                    hold=hold,
                    shin_z=shin_z,
                )
            )

    return sorted(
        candidates,
        key=lambda row: (
            row.hold,
            FAMILY_PRIOR.get(row.family, 99),
            row.specifier,
            -row.market_probability,
            row.outcome_id,
        ),
    )


@dataclass(frozen=True)
class FamilyChoice:
    event_id: str
    home: str
    away: str
    family: str
    market_id: str
    market_name: str
    specifier: str
    hold: float
    margin: float
    shin_z: float
    reason: str
    priced_side: str
    priced_odds: float
    priced_probability: float


def choose_market_family(
    event: dict[str, Any],
    max_hold: float = 0.08,
    min_gap: float = 0.005,
) -> FamilyChoice | None:
    """Pick the tightest complete family, or nothing.

    This chooses a market type. It does not choose a winner, and a missing
    result means the prices are too wide or too close to call a family.
    """
    rows = rank_market_candidates(event, max_hold=max_hold)
    if not rows:
        return None

    best_by_key: dict[tuple[str, str, str], MarketCandidate] = {}
    for row in rows:
        key = (row.family, row.market_id, row.specifier)
        current = best_by_key.get(key)
        if current is None or (row.hold, FAMILY_PRIOR.get(row.family, 99)) < (
            current.hold,
            FAMILY_PRIOR.get(current.family, 99),
        ):
            best_by_key[key] = row

    ranked = sorted(
        best_by_key.values(),
        key=lambda row: (row.hold, FAMILY_PRIOR.get(row.family, 99), row.specifier),
    )
    chosen = ranked[0]
    if len(ranked) > 1:
        nxt = ranked[1]
        same_quality = abs(chosen.hold - nxt.hold) < min_gap and FAMILY_PRIOR.get(chosen.family, 99) == FAMILY_PRIOR.get(
            nxt.family, 99
        )
        if same_quality:
            return None
        gap = nxt.hold - chosen.hold
        reason = (
            f"tightest complete {chosen.family} by {gap:.1%} hold"
            if gap >= min_gap
            else f"equal hold; {chosen.family} is the cleaner simplex"
        )
    else:
        reason = f"only complete {chosen.family} under the hold limit"

    priced = min(
        (
            row
            for row in rows
            if (row.family, row.market_id, row.specifier) == (chosen.family, chosen.market_id, chosen.specifier)
        ),
        key=lambda row: row.odds,
    )
    return FamilyChoice(
        event_id=chosen.event_id,
        home=chosen.home,
        away=chosen.away,
        family=chosen.family,
        market_id=chosen.market_id,
        market_name=chosen.market_name,
        specifier=chosen.specifier,
        hold=chosen.hold,
        margin=chosen.margin,
        shin_z=chosen.shin_z,
        reason=reason,
        priced_side=priced.selection,
        priced_odds=priced.odds,
        priced_probability=priced.market_probability,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screen a saved event payload. Read-only; does not book or stake.")
    parser.add_argument("--file", help="JSON file with one event payload")
    parser.add_argument("--max-hold", type=float, default=0.15)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        from test_market_picker import main as run_tests

        return run_tests()
    if not args.file:
        parser.error("--file is required unless --self-test is set")
    if not 0 <= args.max_hold < 0.8:
        parser.error("--max-hold must be between 0 and 0.8")
    with open(args.file, encoding="utf-8") as handle:
        event = json.load(handle)
    if not isinstance(event, dict):
        parser.error("file must contain one event object")
    rows = rank_market_candidates(event, max_hold=args.max_hold)[: args.top]
    print(json.dumps([asdict(row) for row in rows], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
