"""Joint-scenario allocation and tournament utility. No inferred independence."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog, minimize
from scipy.special import ndtri


@dataclass(frozen=True)
class Allocation:
    quantities: np.ndarray
    expected_profit: float
    worst_terminal_wealth: float
    objective: str


def correlated_binary(probabilities, loadings, *, samples=10000, seed=7):
    """Gaussian common-factor stress model, not an empirically fitted election model.

    Negative loadings support Republican contracts against Democratic contracts.
    Chamber outcomes should instead be derived from complete seat-level worlds.
    """
    p, b = np.asarray(probabilities, float), np.asarray(loadings, float)
    if (
        p.shape != b.shape
        or p.ndim != 1
        or samples < 1
        or not np.all(np.isfinite(p))
        or not np.all(np.isfinite(b))
        or np.any((p < 0) | (p > 1))
        or np.any(abs(b) > 1)
    ):
        raise ValueError("invalid factor assumptions")
    rng = np.random.default_rng(seed)
    latent = rng.normal(size=(samples, 1)) * b + rng.normal(size=(samples, len(p))) * np.sqrt(
        1 - b * b
    )
    return (latent < ndtri(p)).astype(float)


def allocate(
    payoffs,
    weights,
    existing_wealth,
    prices,
    max_quantities,
    *,
    budget,
    minimum_wealth,
    objective="log",
):
    """Continuous constrained allocation; round DOWN then recheck before execution.

    existing_wealth is cash + existing holdings' payout in each joint world.
    payoffs includes YES/NO orientation and any authoritative fractional payout.
    prices must be conservative marginal execution costs, including costs.
    All scenarios, including zero-weight stress worlds, constrain minimum wealth.
    """
    a, w, base, c, caps = map(
        lambda x: np.asarray(x, float), (payoffs, weights, existing_wealth, prices, max_quantities)
    )
    if (
        a.ndim != 2
        or w.shape != (len(a),)
        or base.shape != w.shape
        or c.shape != (a.shape[1],)
        or caps.shape != c.shape
        or any(not np.all(np.isfinite(x)) for x in (a, w, base, c, caps))
        or np.any(w < 0)
        or not np.isclose(w.sum(), 1)
        or np.any(c <= 0)
        or np.any(c > 1)
        or np.any(caps < 0)
        or budget < 0
        or minimum_wealth <= 0
        or np.any(a < 0)
        or np.any(a > 1)
        or np.any(base < minimum_wealth)
    ):
        raise ValueError("invalid or already infeasible scenario portfolio")
    edge = a - c
    constraints = [
        {"type": "ineq", "fun": lambda q: budget - c @ q},
        {"type": "ineq", "fun": lambda q: base + edge @ q - minimum_wealth},
    ]
    if objective == "log":

        def fn(q):
            return -w @ np.log(base + edge @ q)

        def jac(q):
            return -(w / (base + edge @ q)) @ edge

        # Scale the objective so solver tolerances are meaningful at 100k wealth.
        scale = float(np.mean(base))
        result = minimize(
            lambda q: scale * fn(q),
            np.zeros(len(c)),
            jac=lambda q: scale * jac(q),
            bounds=list(zip(np.zeros(len(c)), caps)),
            constraints=constraints,
            method="SLSQP",
            options={"maxiter": 1000, "ftol": 1e-8},
        )
    elif objective == "expected_wealth":
        result = linprog(
            -(w @ edge),
            A_ub=np.vstack([c, -edge]),
            b_ub=np.r_[budget, base - minimum_wealth],
            bounds=list(zip(np.zeros(len(c)), caps)),
            method="highs",
        )
    else:
        raise ValueError("objective must be log or expected_wealth")
    if not result.success:
        raise ValueError("allocation did not converge")
    q = np.maximum(result.x, 0)
    terminal = base + edge @ q
    if c @ q > budget + 1e-5 or min(terminal) < minimum_wealth - 1e-5:
        raise ValueError("allocation violates constraints")
    return Allocation(q, float(w @ edge @ q), float(min(terminal)), objective)


def prize_expectation(wealth, opponents, weights, prizes=(30000, 5000, 2500)):
    """Scenario-aligned opponents; ties split occupied prizes per official rules.

    Opponent terminal wealth must be an explicit assumption, not today's ranks.
    """
    own, others, w = map(lambda x: np.asarray(x, float), (wealth, opponents, weights))
    if (
        own.ndim != 1
        or others.ndim != 2
        or len(others) != len(own)
        or w.shape != own.shape
        or not np.isclose(w.sum(), 1)
        or np.any(w < 0)
        or any(not np.all(np.isfinite(x)) for x in (own, others, w))
    ):
        raise ValueError("invalid tournament scenarios")
    payouts = []
    for x, row in zip(own, others):
        ahead, tied = int(sum(row > x)), int(sum(row == x)) + 1
        payouts.append(sum(prizes[ahead : ahead + tied]) / tied)
    return float(w @ np.asarray(payouts))
