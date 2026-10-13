"""Pure research utilities. All prices are SUSQies/share in [0, 1].

Research predictions are inputs, not claims about real election probabilities.
The model deliberately avoids using dependent forecasts as independent votes.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, log, sqrt
from typing import Iterable


def clamp(x: float, lo: float = 1e-6, hi: float = 1 - 1e-6) -> float:
    if not lo < hi:
        raise ValueError("invalid bounds")
    return max(lo, min(hi, x))


def logit(p: float) -> float:
    p = clamp(p)
    return log(p / (1 - p))


def logistic(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1 / (1 + z)
    z = exp(x)
    return z / (1 + z)


@dataclass(frozen=True)
class Forecast:
    source: str
    probability: float
    reliability: float = 1.0
    # Forecasts within the same dependence group may share data/model inputs.
    group: str = "other"

    def __post_init__(self) -> None:
        if not 0 <= self.probability <= 1 or self.reliability <= 0:
            raise ValueError("invalid forecast")


@dataclass(frozen=True)
class Estimate:
    fair_probability: float
    uncertainty: float
    source_count: int


def blend_forecasts(
    forecasts: Iterable[Forecast],
    *,
    shrink_to: float = 0.5,
    prior_weight: float = 0.5,
    minimum_uncertainty: float = 0.04,
) -> Estimate:
    """Group correlated sources before aggregation; shrink sparse consensus.

    A robust heuristic, *not* statistically fitted or calibrated. Forecast
    disagreement is not equivalent to forecast error; minimum_uncertainty
    protects against false precision.
    """
    fs = list(forecasts)
    if not fs:
        raise ValueError("at least one forecast required")
    if prior_weight < 0 or minimum_uncertainty < 0:
        raise ValueError("invalid tuning parameters")
    groups: dict[str, list[Forecast]] = {}
    for f in fs:
        groups.setdefault(f.group, []).append(f)
    group_estimates = []
    for vals in groups.values():
        weight = sum(v.reliability for v in vals)
        group_estimates.append((
            sum(v.reliability * logit(v.probability) for v in vals) / weight,
            max(v.reliability for v in vals),
        ))
    total = prior_weight + sum(w for _, w in group_estimates)
    center = (prior_weight * logit(shrink_to) + sum(x * w for x, w in group_estimates)) / total
    p = logistic(center)
    disagreement = (
        sqrt(sum(w * (logistic(x) - p) ** 2 for x, w in group_estimates)
             / sum(w for _, w in group_estimates))
        if group_estimates else 0.0
    )
    return Estimate(p, max(minimum_uncertainty, disagreement), len(fs))


@dataclass(frozen=True)
class Level:
    price: float
    quantity: int

    def __post_init__(self) -> None:
        if not (0 <= self.price <= 1) or self.quantity <= 0:
            raise ValueError("invalid book level")


@dataclass(frozen=True)
class FillQuote:
    quantity: int
    total_cost: float
    avg_price: float
    marginal_price: float


def walk_asks(asks: Iterable[Level], target_qty: int, *, limit: float = 1.0) -> FillQuote | None:
    """Simulate taking quoted asks; refuse partial or over-limit orders."""
    if target_qty <= 0:
        raise ValueError("target_qty must be positive")
    if not 0 <= limit <= 1:
        raise ValueError("invalid price limit")
    remaining, cost, marginal = target_qty, 0.0, 0.0
    for level in sorted(asks, key=lambda x: x.price):
        if level.price > limit:
            break
        qty = min(remaining, level.quantity)
        cost += qty * level.price
        remaining -= qty
        marginal = level.price
        if remaining == 0:
            return FillQuote(target_qty, cost, cost / target_qty, marginal)
    return None


@dataclass(frozen=True)
class Opportunity:
    side: str
    estimate: Estimate
    quantity: int
    quote: FillQuote
    conservative_edge: float
    expected_pnl: float
    worst_case_loss: float


def scan_yes_no(
    yes_asks: Iterable[Level],
    no_asks: Iterable[Level],
    estimate: Estimate,
    *,
    max_qty: int = 1000,
    max_cost: float = 2000.0,
    haircut: float = 1.0,
    min_conservative_edge: float = 0.02,
) -> list[Opportunity]:
    """Evaluate executable average-price opportunity on both complementary sides.

    Haircut = uncertainty multiplier. Estimated probability for YES is lowered
    by haircut*uncertainty; for NO, raised accordingly. This is not a confidence
    interval; calibrate uncertainty empirically before trusting sizes.
    """
    if max_qty <= 0 or max_cost <= 0 or haircut < 0 or min_conservative_edge < 0:
        raise ValueError("invalid scan settings")
    results = []
    for side, levels, probability in (
        ("YES", yes_asks, estimate.fair_probability),
        ("NO", no_asks, 1 - estimate.fair_probability),
    ):
        conservative_probability = max(0.0, probability - haircut * estimate.uncertainty)
        for q in (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000):
            if q > max_qty:
                break
            quote = walk_asks(levels, q)
            if quote is None or quote.total_cost > max_cost:
                continue
            conservative_edge = conservative_probability - quote.avg_price
            if conservative_edge >= min_conservative_edge:
                results.append(Opportunity(
                    side, estimate, q, quote, conservative_edge,
                    q * (probability - quote.avg_price), quote.total_cost,
                ))
    return sorted(results, key=lambda x: x.quantity * x.conservative_edge, reverse=True)


def kelly_fraction(p: float, cost: float, *, fractional: float = 0.25) -> float:
    """Unconstrained fractional Kelly for one binary bet; NOT a portfolio optimizer."""
    if not 0 <= p <= 1 or not 0 < cost < 1 or not 0 <= fractional <= 1:
        raise ValueError("invalid Kelly inputs")
    return fractional * max(0.0, (p - cost) / (1 - cost))


def brier(probs: Iterable[float], outcomes: Iterable[int]) -> float:
    ps, ys = list(probs), list(outcomes)
    if not ps or len(ps) != len(ys) or any(y not in (0, 1) for y in ys):
        raise ValueError("probabilities and binary outcomes required")
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def logloss(probs: Iterable[float], outcomes: Iterable[int]) -> float:
    ps, ys = list(probs), list(outcomes)
    if not ps or len(ps) != len(ys) or any(y not in (0, 1) for y in ys):
        raise ValueError("probabilities and binary outcomes required")
    return -sum(y * log(clamp(p)) + (1 - y) * log(1 - clamp(p))
                for p, y in zip(ps, ys)) / len(ps)
