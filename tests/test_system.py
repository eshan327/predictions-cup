import json
from decimal import Decimal as D

import pytest

from predictions_cup.collection import reconcile
from predictions_cup.forecast import ForecastRecord, estimate_asof
from predictions_cup.models import AccountState, Book, Holding, normalize_book
from predictions_cup.paper import Intent, Limits, PaperBroker
from predictions_cup.store import Store
from predictions_cup.strategy import propose


def account(**kwargs):
    return AccountState(
        tournament="t",
        received=100,
        cash=D(1000),
        reserved_buys=0,
        holdings=(),
        reconciled=True,
        issues=(),
        **kwargs,
    )


def book(**kwargs):
    values = dict(
        tournament="t",
        exchange_id="1",
        market_id="2",
        received=103,
        source_at=103,
        sequence=11,
        bids=[{"price": ".4", "quantity": "100"}],
        asks=[{"price": ".5", "quantity": "100"}],
    )
    return Book(**(values | kwargs))


def intent(**kwargs):
    return Intent(
        **(
            dict(
                key="a",
                tournament="t",
                exchange_id="1",
                side="YES",
                quantity=50,
                limit=".5",
                submitted=100,
                expires=130,
                decision_sequence=10,
            )
            | kwargs
        )
    )


def limits(**kwargs):
    return Limits(
        **(
            dict(
                reserve_cash=100,
                max_order_cost=100,
                max_added_cost=200,
                kill_file="/tmp/no-pcup-test-kill",
            )
            | kwargs
        )
    )


def test_complement_book_and_schema_failures():
    b = book()
    assert b.offers("NO")[0].price == D(".6")
    assert b.bids_for("NO")[0].price == D(".5")
    with pytest.raises(ValueError):
        book(bids=[{"price": ".6", "quantity": 1}])
    with pytest.raises(ValueError):
        book(asks=[{"price": "NaN", "quantity": 1}])
    with pytest.raises(ValueError):
        normalize_book(
            {
                "asOf": None,
                "exchangeId": "1",
                "marketId": "2",
                "bids": [],
                "asks": [],
                "bestBid": 0.5,
                "bestAsk": None,
            },
            "t",
            100,
        )


def test_delayed_partial_ioc_persistence_and_no_reused_liquidity(tmp_path):
    path = tmp_path / "p.sqlite"
    with Store(path) as s:
        p = PaperBroker(s, account(), limits())
        assert p.submit(intent(), now=100, end_at=200)
        assert not p.submit(intent(), now=100, end_at=200)
        p.on_book(book(received=101, source_at=101), now=101)
        assert p.cash == 1000
        p.on_book(book(), now=103)
        assert p.cash == D("987.5")
        assert p.inventory == {"1": D(25)}
    with Store(path) as s:
        p = PaperBroker(s, account(), limits())
        assert p.cash == D("987.5")
        p.submit(intent(key="b", submitted=103), now=103, end_at=200)
        p.on_book(book(received=106, source_at=106), now=106)
        assert p.cash == D("987.5")
        assert not p.pending


@pytest.mark.parametrize(
    "change",
    [
        dict(source_at=None),
        dict(sequence=None),
        dict(source_at=101),
        dict(source_at=1000),
        dict(sequence=9),
    ],
)
def test_invalid_execution_book_never_fills(tmp_path, change):
    with Store(tmp_path / "p.sqlite") as s:
        p = PaperBroker(s, account(), limits())
        p.submit(intent(), now=100, end_at=200)
        p.on_book(book(**change), now=103)
        assert p.cash == 1000
        assert p.inventory == {}


def test_kill_cash_opposite_side_and_expiry(tmp_path):
    stop = tmp_path / "STOP"
    with Store(tmp_path / "p.sqlite") as s:
        p = PaperBroker(s, account(), limits(kill_file=str(stop)))
        with pytest.raises(ValueError):
            p.submit(intent(quantity=201), now=100, end_at=200)
        with pytest.raises(ValueError):
            p.submit(intent(action="sell"), now=100, end_at=200)
        p.submit(intent(), now=100, end_at=200)
        with pytest.raises(ValueError):
            p.submit(intent(key="opposite", side="NO"), now=100, end_at=200)
        stop.touch()
        p.on_book(book(), now=103)
        assert not p.pending and p.cash == 1000
        with pytest.raises(ValueError):
            p.submit(intent(key="new"), now=100, end_at=200)


def test_sell_reduces_inventory(tmp_path):
    a = account().model_copy(
        update={
            "holdings": (Holding(exchange_id="1", quantity=-50, cost_basis=20, market_value=20),)
        }
    )
    with Store(tmp_path / "p.sqlite") as s:
        p = PaperBroker(s, a, limits())
        p.submit(intent(side="NO", action="sell"), now=100, end_at=200)
        p.on_book(book(), now=103)
        assert p.inventory["1"] == -25 and p.cash == D("1012.5")


def test_reconciliation_no_sign_and_cash():
    positions = {
        "positions": [
            {
                "exchangeId": "1",
                "quantity": -10,
                "costBasis": 3,
                "marketValue": 4,
                "lots": [{"side": "NO", "quantity": 10, "entryPrice": 0.3}],
            }
        ],
        "summary": {"totalCostBasis": 3},
    }
    orders = [
        {
            "id": 1,
            "tournamentId": "t",
            "side": "no",
            "action": "buy",
            "open": False,
            "quantity": 10,
            "priceLimit": 0.3,
            "exchangeId": "1",
        }
    ]
    fills = [
        {
            "id": 2,
            "orderId": 1,
            "side": "no",
            "quantity": -10,
            "price": 0.3,
            "exchangeId": "1",
            "filledAt": "2026-10-13T00:00:00Z",
        }
    ]
    a = reconcile("t", 97, positions, orders, fills, initial_balance=100, received=100)
    assert a.reconciled
    assert not reconcile(
        "t", 96, positions, orders, fills, initial_balance=100, received=100
    ).reconciled
    assert not reconcile(
        "t", 97, positions, [], fills, initial_balance=100, received=100
    ).reconciled


def record(**kwargs):
    return ForecastRecord(
        **(
            dict(
                exchange_id="1",
                tournament="t",
                source="model",
                source_url="https://example.com",
                dependency_group="polls",
                published_at=90,
                observed_at=99,
                expires_at=200,
                probability=0.8,
                lower=0.7,
                upper=0.9,
                settlement_sha256="a" * 64,
                artifact_sha256="b" * 64,
                kind="model",
                reviewed=True,
            )
            | kwargs
        )
    )


def test_forecasts_no_lookahead_expiry_and_rules_change():
    rs = [record(), record(observed_at=110, probability=0.9, lower=0.9, upper=0.9)]
    args = dict(exchange_id="1", tournament="t", terms_hash="a" * 64)
    assert estimate_asof(rs, now=100, **args)["probability"] == 0.8
    assert estimate_asof(rs, now=201, **args) is None
    assert estimate_asof(rs, now=95, **args) is None
    assert estimate_asof(rs, now=100, **(args | {"terms_hash": "c" * 64})) is None
    assert estimate_asof([record(reviewed=False)], now=100, **args) is None


def test_strategy_requires_evidence_and_uses_worst_price():
    m = {"reviewed": True, "status": "open", "end_at": 300, "settlement_sha256": "a" * 64}
    assert propose(book(), [], m, now=103) is None
    i = propose(book(), [record()], m, now=103)
    assert i.side == "YES" and i.limit == D(".5")
    assert propose(book(), [record(lower=0.49)], m, now=103) is None


def test_raw_capture_redacts_account_metadata(tmp_path):
    with Store(tmp_path / "s.sqlite") as s:
        s.capture(
            "/account",
            {},
            {"email": "private", "balance": 1, "buyingPower": 1, "availableAdvance": 0},
            "a",
            "b",
        )
        body = json.loads(s.db.execute("SELECT body FROM observations").fetchone()[0])
        assert "email" not in body


def test_repeated_depth_not_replenished_by_new_sequence(tmp_path):
    with Store(tmp_path / "p.sqlite") as s:
        p = PaperBroker(s, account(), limits())
        p.submit(intent(), now=100, end_at=200)
        p.on_book(book(), now=103)
        p.submit(intent(key="b", submitted=104), now=104, end_at=200)
        p.on_book(book(received=107, source_at=107, sequence=12), now=107)
        assert p.inventory["1"] == 25
        p.submit(intent(key="c", submitted=108), now=108, end_at=200)
        p.on_book(
            book(received=111, source_at=111, sequence=13, asks=[{"price": ".5", "quantity": 120}]),
            now=111,
        )
        assert p.inventory["1"] == 30


def test_concurrent_paper_writers_rejected(tmp_path):
    with Store(tmp_path / "p.sqlite") as s1, Store(tmp_path / "p.sqlite") as s2:
        one = PaperBroker(s1, account(), limits())
        two = PaperBroker(s2, account(), limits())
        one.submit(intent(), now=100, end_at=200)
        with pytest.raises(ValueError, match="concurrent"):
            two.submit(intent(key="other"), now=100, end_at=200)


def test_authoritative_settlement_and_restart(tmp_path):
    with Store(tmp_path / "p.sqlite") as s:
        p = PaperBroker(s, account(), limits())
        p.submit(intent(), now=100, end_at=200)
        p.on_book(book(), now=103)
        p.settle("1", yes_payout=1, no_payout=0, event_id="s1", source="test-authority")
        assert p.cash == D("1012.5") and p.inventory["1"] == 0
        assert not p.settle("1", yes_payout=1, no_payout=0, event_id="s1", source="test-authority")
        q = PaperBroker(s, account(), limits())
        assert q.cash == p.cash
        with pytest.raises(ValueError, match="settled"):
            q.submit(intent(key="bad"), now=100, end_at=200)


def test_open_real_orders_block_paper_seed(tmp_path):
    with Store(tmp_path / "p.sqlite") as s:
        with pytest.raises(ValueError):
            PaperBroker(s, account().model_copy(update={"open_order_count": 1}), limits())
