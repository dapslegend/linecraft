#!/usr/bin/env python3
"""Odds-as-signal math, copied from the weekend research folder.

The original scanner pulled a bookmaker feed and posted share codes. This
copy keeps the public price math only: implied probability, proportional
de-vig, Shin de-vig, entropy, and KL. It does not place a wager.
"""

from __future__ import annotations

import math


def implied(odds: float) -> float:
    if odds <= 1.0:
        raise ValueError(f"odds must be > 1, got {odds}")
    return 1.0 / odds


def proportional_devig(raw: list[float]) -> list[float]:
    """Flat overround removal. Fair when every outcome is shaded equally."""
    total = sum(raw)
    if total <= 0:
        raise ValueError("empty probability vector")
    return [p / total for p in raw]


def shin_devig(raw: list[float], tol: float = 1e-12, max_iter: int = 80) -> tuple[list[float], float]:
    """Shin (1992) de-vig.

    The book posts prices as if a fraction z of money is informed. Solving

        sum_i (sqrt(z^2 + 4(1-z) * q_i^2) - z) / (2(1-z)) = 1

    for z, then backing out fair probabilities, puts more of the margin on
    the longshot. That is the favourite-longshot bias a retail book bakes in.

    Returns (fair probabilities, z). z near 0 means a tight, symmetric book.
    z above ~0.03 means the short price is shaded and the longshot is the
    one carrying the juice.
    """
    if any(q <= 0 for q in raw):
        raise ValueError("Shin requires positive implied probabilities")
    n = len(raw)
    if n < 2:
        raise ValueError("need at least two outcomes")

    def fair_from_z(z: float) -> list[float]:
        if z <= 0:
            return proportional_devig(raw)
        scale = 2.0 * (1.0 - z)
        out = []
        for q in raw:
            disc = z * z + 4.0 * (1.0 - z) * q * q
            out.append((math.sqrt(disc) - z) / scale)
        return out

    def gap(z: float) -> float:
        return sum(fair_from_z(z)) - 1.0

    # z = 0 is proportional. The upper bound is the smallest raw probability,
    # because a larger z makes the longshot fair probability non-positive.
    lo = 0.0
    hi = min(raw) * 0.999
    if gap(hi) > 0:
        # Margin is so small that Shin collapses to proportional.
        fair = proportional_devig(raw)
        return fair, 0.0
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
    fair = [p / total for p in fair]
    return fair, z


def entropy(probs: list[float]) -> float:
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log(p, 2)
    return h


def kl(p: list[float], q: list[float]) -> float:
    """KL(p || q) in nats. q is one fair price, p is the other market."""
    total = 0.0
    for pi, qi in zip(p, q):
        if pi <= 0:
            continue
        if qi <= 0:
            return float("inf")
        total += pi * math.log(pi / qi)
    return total


def _self_test() -> None:
    raw = [implied(1.50), implied(3.40), implied(7.00)]
    fair, z = shin_devig(raw)
    if abs(sum(fair) - 1.0) > 1e-9:
        raise SystemExit("shin probabilities must sum to 1")
    if z <= 0:
        raise SystemExit("expected a positive insider fraction on a shaded book")
    if fair[-1] / raw[-1] >= fair[0] / raw[0]:
        raise SystemExit("shin should shade the longshot more than the favourite")
    if entropy(fair) <= 0:
        raise SystemExit("entropy should be positive")
    if kl(fair, proportional_devig(raw)) < 0:
        raise SystemExit("kl cannot be negative")
    print("odds_signal self-test ok")


if __name__ == "__main__":
    _self_test()
