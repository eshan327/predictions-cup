import pytest

from predictions_cup.portfolio import Scenario, reject_invalid_scenarios
from predictions_cup.research import Estimate, Forecast, Level, brier, logloss, scan_yes_no


@pytest.mark.parametrize("score", [brier, logloss])
@pytest.mark.parametrize("p", [-0.01, 1.01, float("nan"), float("inf")])
def test_invalid_probabilities_rejected(score, p):
    with pytest.raises(ValueError):
        score([p], [1])


def test_generator_book_not_exhausted_by_first_quote():
    choices = scan_yes_no((x for x in [Level(0.1, 1000)]), [], Estimate(0.9, 0.1, 1))
    assert choices[0].quantity == 1000


def test_missing_scenario_outcome_is_not_false():
    with pytest.raises(ValueError):
        reject_invalid_scenarios([Scenario("missing", 1, {"A": False})], implications=[("A", "B")])


def test_infinite_forecast_weight_rejected():
    with pytest.raises(ValueError):
        Forecast("bad", 0.5, reliability=float("inf"))
