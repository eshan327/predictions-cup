from math import isclose
import pytest
from predictions_cup.portfolio import (
    Position, Scenario, analyze, independent_scenarios,
    reject_invalid_scenarios, recommend_max_additional_cost,
)


def test_existing_inventory_and_joint_worlds():
    held = [
        Position("ME", "YES", 17318, .577),
        Position("NY17", "YES", 12638, .633),
        Position("SEN", "NO", 26548, .565),
    ]
    all_win = Scenario("all wins", .5, {"ME": True, "NY17": True, "SEN": False})
    all_lose = Scenario("all losses", .5, {"ME": False, "NY17": False, "SEN": True})
    report = analyze(held, [all_win, all_lose])
    assert isclose(report.committed, 32991.96)
    assert report.worst_pnl < -32000
    assert report.best_pnl > 23000
    assert isclose(report.probability_of_loss, .5)
    assert report.loss_cvar_95 > 32000
    assert recommend_max_additional_cost(100000, held) > 0


def test_independence_explicit_and_implications():
    worlds = independent_scenarios({"A": .4, "B": .6})
    assert len(worlds) == 4
    assert isclose(sum(x.probability for x in worlds), 1)
    filtered = reject_invalid_scenarios(worlds, implications=[("A", "B")])
    assert len(filtered) == 3
    assert isclose(sum(x.probability for x in filtered), 1)
    assert all(not (s.outcomes["A"] and not s.outcomes["B"]) for s in filtered)


def test_incomplete_scenario_fails():
    with pytest.raises(ValueError):
        analyze([Position("A", "YES", 1, .3)], [Scenario("broken", 1, {})])
