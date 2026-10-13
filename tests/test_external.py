import pytest

from predictions_cup.external import parse_rtwh
from predictions_cup.models import timestamp


def payload():
    return {
        "data": [
            [["", "Democrats", "Republicans"], ["Chance to Win", "60% Chance", "40% Chance"]],
            [["Last Updated on Oct 12, 10:49 PM ET"]],
            [["", "D", "R", "Ind"], ["Maine", "Candidate: 70%", "Other: 30%", ""]],
        ]
    }


def test_source_timestamp_and_dynamic_sheet_order():
    d = payload()
    d["data"].reverse()
    r = parse_rtwh(d, timestamp("2026-10-13T05:00:00Z"))
    assert r["probabilities"]["Maine/D"] == 0.7
    assert r["published_at"] == timestamp("2026-10-13T02:49:00Z")
    assert r["observed_at"] > r["published_at"]


def test_stale_future_or_changed_source_fails():
    for observed in ["2026-10-12T01:00:00Z", "2026-10-20T01:00:00Z"]:
        with pytest.raises(ValueError):
            parse_rtwh(payload(), timestamp(observed))
    d = payload()
    d["data"][0][1][2] = "50% Chance"
    with pytest.raises(ValueError):
        parse_rtwh(d, timestamp("2026-10-13T05:00:00Z"))
