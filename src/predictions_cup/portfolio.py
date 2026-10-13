"""Joint-outcome risk, existing inventory and scenario-based candidate evaluation.

These are explicit *assumed* scenarios, not fitted election probabilities.
All P&L is terminal settlement P&L, not mark-to-market.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Position:
    contract: str
    side: str
    shares: int
    average_cost: float

    def __post_init__(self) -> None:
        if self.side not in ("YES", "NO") or self.shares < 0:
            raise ValueError("invalid position")
        if not 0 <= self.average_cost <= 1:
            raise ValueError("invalid cost")

    @property
    def basis(self) -> float:
        return self.shares * self.average_cost

    def pnl(self, resolves_yes: bool) -> float:
        wins = resolves_yes if self.side == "YES" else not resolves_yes
        return self.shares * (float(wins) - self.average_cost)


@dataclass(frozen=True)
class Scenario:
    name: str
    probability: float
    outcomes: dict[str, bool]

    def __post_init__(self) -> None:
        if not 0 <= self.probability <= 1:
            raise ValueError("invalid scenario probability")


@dataclass(frozen=True)
class RiskReport:
    committed: float
    expected_pnl: float
    worst_pnl: float
    best_pnl: float
    probability_of_loss: float
    loss_cvar_95: float
    scenarios: tuple[tuple[str, float, float], ...]


def analyze(positions: list[Position], scenarios: list[Scenario]) -> RiskReport:
    if not scenarios or abs(sum(x.probability for x in scenarios) - 1) > 1e-8:
        raise ValueError("scenario weights must sum to one")
    required = {p.contract for p in positions}
    if any(not required.issubset(s.outcomes) for s in scenarios):
        raise ValueError("some scenarios omit held contracts")
    outcomes = [(s.name, s.probability,
                 sum(pos.pnl(s.outcomes[pos.contract]) for pos in positions))
                for s in scenarios]
    expected = sum(weight * pnl for _, weight, pnl in outcomes)
    # CVaR is the weighted average of the worst 5% of P&L.
    tail_mass, tail_pnl = .05, 0.0
    for _, weight, pnl in sorted(outcomes, key=lambda row: row[2]):
        taken = min(weight, tail_mass)
        tail_pnl += taken * pnl
        tail_mass -= taken
        if tail_mass <= 1e-12:
            break
    return RiskReport(
        committed=sum(p.basis for p in positions),
        expected_pnl=expected,
        worst_pnl=min(x[2] for x in outcomes),
        best_pnl=max(x[2] for x in outcomes),
        probability_of_loss=sum(w for _, w, pnl in outcomes if pnl < 0),
        loss_cvar_95=-(tail_pnl / .05),
        scenarios=tuple(outcomes),
    )


def independent_scenarios(probabilities: dict[str, float]) -> list[Scenario]:
    """Baseline ONLY: mathematically independent, generally false for elections."""
    if len(probabilities) > 16:
        raise ValueError("independent enumeration restricted to 16 contracts")
    if any(not 0 <= p <= 1 for p in probabilities.values()):
        raise ValueError("invalid probability")
    keys = list(probabilities)
    output = []
    for bits in product((False, True), repeat=len(keys)):
        weight = 1.0
        for key, bit in zip(keys, bits):
            p = probabilities[key]
            weight *= p if bit else (1 - p)
        output.append(Scenario(
            name=",".join(f"{key}={int(bit)}" for key, bit in zip(keys, bits)),
            probability=weight,
            outcomes=dict(zip(keys, bits)),
        ))
    return output


def reject_invalid_scenarios(
    scenarios: list[Scenario], *, implications: list[tuple[str, str]]
) -> list[Scenario]:
    """If event A implies event B, remove worlds where A is true and B false.

    Reweighting is a conditional scenario distribution, NOT arbitrage by itself.
    """
    valid = [
        s for s in scenarios
        if not any(s.outcomes.get(a, False) and not s.outcomes.get(b, False)
                   for a, b in implications)
    ]
    weight = sum(x.probability for x in valid)
    if weight <= 0:
        raise ValueError("all scenarios invalid")
    return [Scenario(s.name, s.probability / weight, s.outcomes) for s in valid]


def recommend_max_additional_cost(
    initial_bankroll: float,
    existing: list[Position],
    *,
    gross_fraction_limit: float = .4,
    cash_reserve_fraction: float = .5,
) -> float:
    """Simple conservative cash/basis budget, NOT a risk-aware portfolio optimizer."""
    if initial_bankroll <= 0 or not 0 <= gross_fraction_limit <= 1:
        raise ValueError("invalid limits")
    if not 0 <= cash_reserve_fraction <= 1:
        raise ValueError("invalid reserve fraction")
    committed = sum(x.basis for x in existing)
    return max(0.0, min(
        initial_bankroll * gross_fraction_limit - committed,
        initial_bankroll * (1 - cash_reserve_fraction) - committed,
    ))
