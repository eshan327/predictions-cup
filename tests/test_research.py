from math import isclose
import pytest
from predictions_cup.research import (
    Forecast, Level, blend_forecasts, walk_asks, scan_yes_no,
    kelly_fraction, brier, logloss,
)


def test_book_sweep_and_partial_rejection():
    book = [Level(.7, 20), Level(.5, 10)]
    q = walk_asks(book, 15)
    assert q is not None
    assert isclose(q.total_cost, 8.5)
    assert isclose(q.avg_price, 8.5 / 15)
    assert walk_asks(book, 31) is None
    assert walk_asks(book, 15, limit=.5) is None


def test_ensemble_groups_and_uncertainty_floor():
    est = blend_forecasts([
        Forecast("A", .7, group="shared"),
        Forecast("B", .7, group="shared"),
        Forecast("C", .6, group="independent"),
    ])
    assert .5 < est.fair_probability < .7
    assert est.uncertainty >= .04


def test_scanner_refuses_marginal_unavailable_depth():
    estimate = blend_forecasts([Forecast("A", .9)], prior_weight=0)
    choices = scan_yes_no([Level(.4, 2)], [Level(.8, 100)], estimate, max_qty=100)
    assert choices
    assert all(c.quantity <= 2 for c in choices)
    assert all(c.side == "YES" for c in choices)


def test_calibration_metrics():
    assert brier([1, 0], [1, 0]) == 0
    assert logloss([.9], [1]) > 0
    assert kelly_fraction(.6, .5) > 0
    with pytest.raises(ValueError):
        brier([], [])


def test_prices_validate():
    with pytest.raises(ValueError):
        Level(1.1, 1)
    with pytest.raises(ValueError):
        Forecast("bad", -0.1)
