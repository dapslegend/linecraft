"""Closed-form price analysis for a single complete market.

Prices are decimal odds. A complete market lists every mutually exclusive
outcome. Overlapping markets (double chance, Asian lines that are not a
simplex) are rejected rather than de-vigged as if they were independent.
"""

from __future__ import annotations

import math
from typing import Any

MAX_OUTCOMES = 24
MAX_ODDS = 1001.0


class PriceError(ValueError):
    """Caller sent a market that cannot be analysed safely."""


def implied(odds: float) -> float:
    if not math.isfinite(odds) or odds <= 1.0 or odds > MAX_ODDS:
        raise PriceError(f"odds must be finite and in (1, {MAX_ODDS}]")
    return 1.0 / odds


def proportional_devig(raw: list[float]) -> list[float]:
    """Remove a flat overround. Fair when every outcome is shaded equally."""
    if any(not math.isfinite(q) or q <= 0 for q in raw):
        raise PriceError("implied probabilities must be finite and positive")
    total = sum(raw)
    if total <= 0:
        raise PriceError("empty probability vector")
    return [q / total for q in raw]


def shin_devig(raw: list[float], tol: float = 1e-12, max_iter: int = 80) -> tuple[list[float], float]:
    """Shin (1992) de-vig.

    The book posts prices as if a fraction z of money is informed. Solving
    for z, then backing out fair probabilities, puts more of the margin on
    the longshot. z near 0 is a tight book. z above about 0.03 means the
    short price is shaded and the longshot carries the juice.

    Returns (fair probabilities, z).
    """
    if any(not math.isfinite(q) or q <= 0 for q in raw):
        raise PriceError("Shin requires positive finite implied probabilities")
    if len(raw) < 2:
        raise PriceError("need at least two outcomes")

    def fair_from_z(z: float) -> list[float]:
        if z <= 0:
            return proportional_devig(raw)
        scale = 2.0 * (1.0 - z)
        out = []
        for q in raw:
            disc = z * z + 4.0 * (1.0 - z) * q * q
            if disc < 0:
                raise PriceError("Shin discriminant went negative")
            out.append((math.sqrt(disc) - z) / scale)
        return out

    def gap(z: float) -> float:
        return sum(fair_from_z(z)) - 1.0

    lo = 0.0
    hi = min(raw) * 0.999
    if hi <= 0:
        raise PriceError("cannot bound Shin insider fraction")
    if gap(hi) > 0:
        return proportional_devig(raw), 0.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if gap(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    z = 0.5 * (lo + hi)
    fair = fair_from_z(z)
    total = sum(fair)
    if total <= 0:
        raise PriceError("Shin fair probabilities did not sum")
    return [p / total for p in fair], z


def entropy_bits(probs: list[float]) -> float:
    total = 0.0
    for p in probs:
        if p > 0:
            total -= p * math.log(p, 2)
    return total


def _as_odds(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PriceError(f"{field} must be a number")
    odds = float(value)
    if not math.isfinite(odds):
        raise PriceError(f"{field} must be finite")
    return odds


def analyse_market(outcomes: list[dict[str, Any]], method: str = "shin") -> dict[str, Any]:
    """De-vig one complete market and report hold, margin, and entropy.

    Each outcome needs a non-empty name and decimal odds greater than 1.
    Names must be unique inside the market.
    """
    if method not in ("shin", "proportional"):
        raise PriceError("method must be 'shin' or 'proportional'")
    if not isinstance(outcomes, list) or not 2 <= len(outcomes) <= MAX_OUTCOMES:
        raise PriceError(f"a complete market needs 2 to {MAX_OUTCOMES} outcomes")

    names: list[str] = []
    odds: list[float] = []
    seen: set[str] = set()
    for index, item in enumerate(outcomes):
        if not isinstance(item, dict):
            raise PriceError(f"outcome {index} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise PriceError(f"outcome {index} needs a name of 1 to 80 characters")
        name = name.strip()
        key = name.casefold()
        if key in seen:
            raise PriceError(f"duplicate outcome name: {name}")
        seen.add(key)
        names.append(name)
        odds.append(_as_odds(item.get("odds"), f"outcome {index} odds"))

    raw = [implied(price) for price in odds]
    overround = sum(raw)
    if overround < 1.0:
        raise PriceError("overround below 1 is an arbitrage, not a shaded book; refused")
    if method == "shin":
        fair, z = shin_devig(raw)
    else:
        fair, z = proportional_devig(raw), 0.0

    rows = []
    for name, price, q, p in zip(names, odds, raw, fair):
        rows.append(
            {
                "name": name,
                "odds": round(price, 4),
                "implied": round(q, 6),
                "fair": round(p, 6),
                "fair_odds": round(1.0 / p, 4) if p > 0 else None,
                "edge_vs_posted": round(p - q, 6),
            }
        )
    longest = max(rows, key=lambda row: row["odds"])
    shortest = min(rows, key=lambda row: row["odds"])
    return {
        "method": method,
        "outcomes": rows,
        "overround": round(overround, 6),
        "hold": round(1.0 - 1.0 / overround, 6),
        "margin": round(overround - 1.0, 6),
        "shin_z": round(z, 6),
        "entropy_bits": round(entropy_bits(fair), 6),
        "longest": longest["name"],
        "shortest": shortest["name"],
        "note": "Analysis of posted prices only. This is not a wager and not a prediction market.",
    }
