"""Replay observed books in receipt order, without inventing historical depth."""

import json
from pathlib import Path

from predictions_cup.models import AccountState, Book
from predictions_cup.operations import account_signature
from predictions_cup.paper import Limits, PaperBroker
from predictions_cup.store import Store
from predictions_cup.strategy import propose


def replay(source, target, records, mappings, *, limits=None):
    if (
        Path(source.db.execute("PRAGMA database_list").fetchone()["file"]).resolve()
        == Path(target).resolve()
    ):
        raise ValueError("paper output must differ from research database")
    row = source.db.execute(
        "SELECT body FROM runs WHERE status='ok' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        raise ValueError("no reconciled account seed")
    run = json.loads(row["body"])
    account = AccountState.model_validate(run["account"])
    limits = limits or Limits()
    if mappings:
        # A mapping is point-in-time too: never backdate a manual rules review.
        if any("observed_at" not in m for m in mappings.values()):
            raise ValueError("mapping availability timestamp required")
    with Store(target) as out:
        if out.db.execute("SELECT COUNT(*) FROM paper_events").fetchone()[0]:
            raise ValueError("use a fresh paper database for deterministic replay")
        broker = PaperBroker(out, account, limits)
        rejected, decisions = 0, 0
        for row in source.db.execute(
            "SELECT body FROM books WHERE tournament=? AND received>=? ORDER BY received,id",
            (account.tournament, run["ended"]),
        ):
            b = Book.model_validate_json(row["body"])
            now = b.received
            checkpoint = source.db.execute(
                "SELECT body,status FROM runs WHERE received<=? ORDER BY received DESC,id DESC LIMIT 1",
                (now,),
            ).fetchone()
            if checkpoint:
                checkpoint_body = json.loads(checkpoint["body"])
                updated = (
                    AccountState.model_validate(checkpoint_body["account"])
                    if "account" in checkpoint_body
                    else None
                )
                if (
                    checkpoint["status"] != "ok"
                    or updated is None
                    or account_signature(updated) != account_signature(account)
                ):
                    for key in list(broker.pending):
                        broker.cancel(key, "authoritative_account_changed")
                    continue
                broker.account = updated
            broker.on_book(b, now=now)
            mapping = mappings.get(b.exchange_id)
            if mapping and mapping["observed_at"] > now:
                continue
            i = propose(b, records, mapping, now=now, max_cost=float(limits.max_order_cost))
            if i:
                decisions += 1
                try:
                    broker.submit(i, now=now, end_at=run["end_at"])
                except ValueError:
                    rejected += 1
        for key in list(broker.pending):
            broker.cancel(key, "end_of_replay_no_future_book")
        return {
            "decisions": decisions,
            "rejected": rejected,
            "cash": str(broker.cash),
            "inventory": {k: str(v) for k, v in broker.inventory.items()},
            "completed_intents": len(broker.completed),
            "added_cost": str(broker.added_cost),
            "profitability_validated": False,
            "execution_model": "latency-delayed IOC with depth participation haircut",
        }
