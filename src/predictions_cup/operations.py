"""Small operational loop: bounded polling, heartbeat, and fail-closed paper mode."""

import json
import time
from pathlib import Path

from predictions_cup.collection import collect
from predictions_cup.models import AccountState, Book
from predictions_cup.paper import Limits, PaperBroker
from predictions_cup.strategy import propose


def account_signature(account):
    return (
        account.tournament,
        account.cash,
        account.reserved_buys,
        account.open_order_count,
        sorted((h.exchange_id, h.quantity, h.cost_basis) for h in account.holdings),
    )


def paper_cycle(client, research_store, paper_store, slug, records, mappings, *, limits=None):
    limits = limits or Limits()
    result = collect(client, research_store, slug, exchange_ids=list(mappings))
    current = AccountState.model_validate(result["account"])
    seed_row = paper_store.db.execute(
        "SELECT body FROM paper_events ORDER BY id LIMIT 1"
    ).fetchone()
    seed = (
        AccountState.model_validate(json.loads(seed_row["body"])["account"])
        if seed_row
        else current
    )
    if (
        not current.reconciled
        or account_signature(seed) != account_signature(current)
        or result["status"] != "active"
        or result["book_errors"]
    ):
        raise ValueError("account changed or unhealthy: stop and create a new paper seed")
    broker = PaperBroker(paper_store, seed, limits)
    broker.account = current
    # Manual review only survives while authoritative terms and lifecycle match.
    verified = {}
    for eid, mapping in mappings.items():
        actual = result.get("mappings", {}).get(eid)
        if actual and actual["settlement_sha256"] == mapping.get("settlement_sha256"):
            verified[eid] = {**mapping, **actual}
    for key, pending in list(broker.pending.items()):
        if pending.exchange_id not in verified:
            broker.cancel(key, "settlement_terms_unverified")
    decisions, rejected = 0, 0
    for r in research_store.db.execute(
        "SELECT body FROM books WHERE received>=? AND tournament=? ORDER BY received,id",
        (result["started"], current.tournament),
    ):
        b = Book.model_validate_json(r["body"])
        now = time.time()
        broker.on_book(b, now=now)
        mapping = verified.get(b.exchange_id)
        if mapping and mapping.get("observed_at", float("inf")) > now:
            continue
        i = propose(b, records, mapping, now=now, max_cost=float(limits.max_order_cost))
        if i:
            decisions += 1
            try:
                broker.submit(i, now=now, end_at=result["end_at"])
            except ValueError:
                rejected += 1
    return {
        "mode": "paper",
        "decisions": decisions,
        "rejected": rejected,
        "cash": str(broker.cash),
        "pending": len(broker.pending),
        "added_cost": str(broker.added_cost),
        "account_reconciled": current.reconciled,
    }


def health(store, *, now=None, max_age=180):
    now = now or time.time()
    row = store.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return {"healthy": False, "reason": "no completed collection"}
    value = json.loads(row["body"])
    age = now - row["received"]
    return {
        "healthy": row["status"] == "ok"
        and 0 <= age <= max_age
        and not Path("STOP").exists()
        and 0 <= now - value.get("account", {}).get("received", 0) <= max_age,
        "age_seconds": age,
        "status": row["status"],
        "account_issues": value.get("account", {}).get("issues", []),
        "book_errors": value.get("book_errors", []),
        "kill_switch": Path("STOP").exists(),
    }
