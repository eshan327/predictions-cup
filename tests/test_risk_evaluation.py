import numpy as np
import pytest

from predictions_cup.evaluation import block_mean_interval, purged_splits, tape_report
from predictions_cup.risk import allocate, correlated_binary, prize_expectation


def test_joint_risk_limits_and_dominated_trade():
    a = np.array([[1, 1], [0, 0]])
    for objective in ["log", "expected_wealth"]:
        r = allocate(
            a,
            [0.8, 0.2],
            [100, 100],
            [0.5, 0.9],
            [100, 100],
            budget=20,
            minimum_wealth=85,
            objective=objective,
        )
        assert r.quantities[1] < 1e-5
        assert 0.5 * r.quantities[0] <= 15 + 1e-5
        assert r.expected_profit > 0 and r.worst_terminal_wealth >= 85 - 1e-5


def test_factor_worlds_preserve_orientation_and_marginals():
    a = correlated_binary([0.5, 0.5], [1, -1], samples=10000)
    assert np.all(a[:, 0] + a[:, 1] == 1)
    assert abs(a[:, 0].mean() - 0.5) < 0.02
    with pytest.raises(ValueError):
        correlated_binary([float("nan")], [0])


def test_tournament_ties_match_official_prizes():
    assert prize_expectation([100], [[100, 90]], [1]) == 17500
    assert prize_expectation([100], [[100, 100]], [1]) == 12500
    assert prize_expectation([100], [[200, 150, 100]], [1]) == 1250


def test_purging_excludes_future_labels():
    t = np.arange(100)
    splits = list(purged_splits(t, t + 10, min_train=20))
    assert splits
    for train, test in splits:
        assert max(t[train] + 10) < min(t[test])


def test_bootstrap_reproducible_and_no_fake_precision():
    with pytest.raises(ValueError):
        block_mean_interval([1, 2, 3])
    r = block_mean_interval(np.arange(100), seed=4)
    assert r == block_mean_interval(np.arange(100), seed=4)
    assert r["lower"] < r["mean"] < r["upper"]


def test_trade_dedup_is_not_execution():
    row = {"id": "1", "createdAt": "2026-10-13T00:00:00Z", "price": 0.5, "size": 10}
    r = tape_report([row, row])
    assert r["trades"] == 1 and r["quantity"] == 10
    assert r["lag1_price_change_correlation"] is None
