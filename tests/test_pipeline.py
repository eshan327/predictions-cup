import json
from decimal import Decimal

import pytest

from predictions_cup.collection import collect
from predictions_cup.models import AccountState, Book
from predictions_cup.operations import health, paper_cycle
from predictions_cup.paper import Intent, Limits, PaperBroker
from predictions_cup.replay import replay
from predictions_cup.store import Store


class FakeAPI:
    def __init__(self, drift=False):
        self.drift = drift

    def get(self, path, params=None):
        if path == "/tournaments/cup":
            return {
                "id": "t",
                "status": "active",
                "initialBalance": 1000,
                "endDate": "2026-11-04T17:00:00Z",
            }
        if path == "/account":
            assert params == {"tournamentId": "t"}
            return {"balance": 1000}
        if path.endswith("/positions"):
            return {"positions": [], "summary": {"totalCostBasis": 0}}
        if path.endswith("/nodes"):
            return {"root": {"contract_details": {"raceId": "1"}}}
        raise AssertionError(path)

    def rows(self, path, params=None):
        if path.endswith("/markets"):
            return [
                {
                    "id": "2",
                    "status": "open",
                    "settlementDate": "2026-11-04T17:00:00Z",
                    "exchanges": [{"id": "1"}],
                }
            ]
        if self.drift and path == "/orders" and params["status"] == "open":
            return [
                {
                    "id": 9,
                    "quantity": 1,
                    "priceLimit": 0.5,
                    "side": "yes",
                    "action": "buy",
                    "open": True,
                }
            ]
        return []

    def get_orderbook(self, eid, tid):
        assert eid == "1" and tid == "t"
        return {
            "exchangeId": "1",
            "marketId": "2",
            "asOf": None,
            "bids": [{"price": 0.4, "quantity": 100}],
            "asks": [{"price": 0.5, "quantity": 100}],
            "bestBid": 0.4,
            "bestAsk": 0.5,
        }


def test_collector_integration_and_order_drift(tmp_path):
    with Store(tmp_path / "s.sqlite") as s:
        r = collect(FakeAPI(), s, "cup", exchange_ids=["1"])
        assert r["account"]["reconciled"] and r["book_count"] == 1
        assert len(r["mappings"]["1"]["settlement_sha256"]) == 64
        assert health(s, now=r["ended"] + 1)["healthy"]
        r = collect(FakeAPI(drift=True), s, "cup", exchange_ids=["1"])
        assert not r["account"]["reconciled"]
        assert not health(s, now=r["ended"] + 1)["healthy"]


def test_replay_does_not_fill_on_decision_book_or_reuse_target(tmp_path):
    with Store(tmp_path / "source.sqlite") as source:
        account = AccountState(
            tournament="t",
            received=100,
            cash=1000,
            reserved_buys=0,
            holdings=(),
            reconciled=True,
            issues=(),
        )
        source.run(
            100, "ok", {"account": account.model_dump(mode="json"), "ended": 100, "end_at": 1000}
        )
        source.add_book(
            Book(
                tournament="t",
                exchange_id="1",
                market_id="2",
                received=101,
                source_at=101,
                sequence=1,
                bids=[],
                asks=[{"price": 0.5, "quantity": 100}],
            )
        )
        result = replay(source, tmp_path / "out.sqlite", [], {})
        assert Decimal(result["cash"]) == 1000 and result["completed_intents"] == 0
        with pytest.raises(ValueError):
            replay(source, tmp_path / "out.sqlite", [], {})
        with pytest.raises(ValueError):
            replay(source, tmp_path / "source.sqlite", [], {})


def test_changed_terms_cancel_pending_before_execution(tmp_path, monkeypatch):
    import predictions_cup.operations as operations

    account = AccountState(
        tournament="t",
        received=100,
        cash=1000,
        reserved_buys=0,
        holdings=(),
        reconciled=True,
        issues=(),
    )
    limits = Limits(reserve_cash=0)
    with Store(tmp_path / "r.sqlite") as research, Store(tmp_path / "p.sqlite") as paper:
        broker = PaperBroker(paper, account, limits)
        broker.submit(
            Intent(
                key="x",
                tournament="t",
                exchange_id="1",
                side="YES",
                quantity=10,
                limit=".5",
                submitted=100,
                expires=130,
                decision_sequence=1,
            ),
            now=100,
            end_at=200,
        )
        result = {
            "started": 100,
            "account": account.model_dump(mode="json"),
            "status": "active",
            "book_errors": [],
            "end_at": 200,
            "mappings": {"1": {"settlement_sha256": "changed"}},
        }
        monkeypatch.setattr(operations, "collect", lambda *a, **k: result)
        paper_cycle(
            None,
            research,
            paper,
            "cup",
            [],
            {"1": {"settlement_sha256": "old", "reviewed": True}},
            limits=limits,
        )
        last = json.loads(
            paper.db.execute("SELECT body FROM paper_events ORDER BY id DESC LIMIT 1").fetchone()[0]
        )
        assert last["reason"] == "settlement_terms_unverified"
        assert last["quantity"] == "0"
