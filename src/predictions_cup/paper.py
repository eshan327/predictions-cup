"""Durable, conservative IOC paper execution. This module cannot send live orders.

Snapshot replay is a counterfactual execution model, not evidence of actual fills.
Passive orders are intentionally unsupported without reliable queue/aggressor data.
"""

import json
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from predictions_cup.models import Model
from predictions_cup.store import encode


def D(x):
    return Decimal(str(x))


class Limits(Model):
    reserve_cash: Decimal = Field(default=Decimal("50000"), ge=0)
    max_order_cost: Decimal = Field(default=Decimal("1000"), gt=0)
    max_added_cost: Decimal = Field(default=Decimal("5000"), gt=0)
    max_book_age: float = Field(default=15, gt=0)
    max_account_age: float = Field(default=180, gt=0)
    latency: float = Field(default=2, ge=0)
    participation: Decimal = Field(default=Decimal(".25"), gt=0, le=1)
    fee_per_share: Decimal = Field(default=Decimal("0"), ge=0)
    kill_file: str = "STOP"


class Intent(Model):
    key: str = Field(min_length=1)
    tournament: str
    exchange_id: str
    side: Literal["YES", "NO"]
    action: Literal["buy", "sell"] = "buy"
    quantity: int = Field(gt=0)
    limit: Decimal = Field(ge=Decimal(".005"), le=Decimal(".995"))
    submitted: float
    expires: float
    decision_sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def tick(self):
        if self.limit % Decimal(".005") or self.expires <= self.submitted:
            raise ValueError("off-tick price or invalid expiry")
        return self


class PaperBroker:
    def __init__(self, store, account, limits=None):
        if not account.reconciled or account.open_order_count:
            raise ValueError("authoritative reconciliation required")
        self.store, self.account, self.limits = store, account, limits or Limits()
        self.cash = account.cash
        self.inventory = {h.exchange_id: h.quantity for h in account.holdings}
        self.pending = {}
        self.completed = set()
        self.added_cost = D(0)
        self.used_versions = set()
        self.consumed = {}
        self.settled = set()
        events = [
            json.loads(r["body"])
            for r in store.db.execute("SELECT body FROM paper_events ORDER BY id")
        ]
        self.revision = len(events)
        seed = account.model_dump(mode="json")
        if events:
            if events[0].get("account") != seed or events[0].get(
                "limits"
            ) != self.limits.model_dump(mode="json"):
                raise ValueError("paper database belongs to a different account seed")
            for event in events[1:]:
                self._apply(event)
        else:
            self._record(
                "seed",
                {"type": "seed", "account": seed, "limits": self.limits.model_dump(mode="json")},
            )

    def _record(self, key, event):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            actual = self.store.db.execute("SELECT COUNT(*) FROM paper_events").fetchone()[0]
            if actual != self.revision:
                raise ValueError("concurrent paper writer; reload state")
            self.store.db.execute(
                "INSERT INTO paper_events(event_key,body) VALUES(?,?)", (key, encode(event))
            )
        self.revision += 1
        self._apply(event)

    def _apply(self, e):
        if e["type"] == "settlement":
            self.cash += D(e["cash_delta"])
            self.inventory[e["exchange_id"]] = D(0)
            self.settled.add(e["exchange_id"])
        elif e["type"] == "submitted":
            i = Intent.model_validate(e["intent"])
            self.pending[i.key] = i
        elif e["type"] == "completed":
            i = self.pending.pop(e["key"])
            qty, cash_delta = D(e["quantity"]), D(e["cash_delta"])
            self.cash += cash_delta
            direction = (1 if i.side == "YES" else -1) * (1 if i.action == "buy" else -1)
            if qty:
                self.inventory[i.exchange_id] = (
                    self.inventory.get(i.exchange_id, D(0)) + qty * direction
                )
            if i.action == "buy":
                self.added_cost -= cash_delta
            if e.get("version") is not None:
                self.used_versions.add((i.exchange_id, e["version"]))
            for level in e.get("filled_levels", []):
                key = (i.exchange_id, i.side, i.action, D(level["price"]))
                self.consumed[key] = self.consumed.get(key, D(0)) + D(level["quantity"])
            self.completed.add(i.key)

    def submit(self, intent, *, now, end_at):
        if intent.key in self.pending:
            if self.pending[intent.key] != intent:
                raise ValueError("idempotency key reused with different intent")
            return False
        if intent.key in self.completed:
            return False
        if intent.exchange_id in self.settled:
            raise ValueError("exchange already settled")
        limits = self.limits
        if (
            Path(limits.kill_file).exists()
            or now >= end_at
            or intent.expires > end_at
            or now != intent.submitted
            or now < self.account.received
            or now - self.account.received > limits.max_account_age
            or intent.tournament != self.account.tournament
        ):
            raise ValueError("paper safety gate blocked order")
        cost = D(intent.quantity) * (intent.limit + limits.fee_per_share)
        reserved = sum(
            (
                D(i.quantity) * (i.limit + limits.fee_per_share)
                for i in self.pending.values()
                if i.action == "buy"
            ),
            D(0),
        )
        signed = self.inventory.get(intent.exchange_id, D(0))
        side_sign = 1 if intent.side == "YES" else -1
        if intent.action == "buy":
            if signed * side_sign < 0 or any(
                i.exchange_id == intent.exchange_id and i.side != intent.side
                for i in self.pending.values()
            ):
                raise ValueError("opposite-side holding/order; explicit close required")
            if (
                cost > limits.max_order_cost
                or self.added_cost + reserved + cost > limits.max_added_cost
                or self.cash - reserved - cost - self.account.reserved_buys < limits.reserve_cash
            ):
                raise ValueError("cash or exposure limit")
        else:
            selling = sum(
                i.quantity
                for i in self.pending.values()
                if i.exchange_id == intent.exchange_id and i.action == "sell"
            )
            if signed * side_sign - selling < intent.quantity:
                raise ValueError("no naked selling")
        self._record(
            "submit:" + intent.key, {"type": "submitted", "intent": intent.model_dump(mode="json")}
        )
        return True

    def cancel(self, key, reason="cancelled"):
        if key in self.pending:
            self._record(
                "complete:" + key,
                {
                    "type": "completed",
                    "key": key,
                    "quantity": "0",
                    "cash_delta": "0",
                    "reason": reason,
                    "version": None,
                },
            )

    def settle(self, exchange_id, *, yes_payout, no_payout, event_id, source):
        """Explicit authoritative payouts; refunds must supply both sides separately.

        Never assume refund = 0.5. Caller must reconcile settlement source first.
        """
        yes, no = D(yes_payout), D(no_payout)
        if not source or not event_id or not 0 <= yes <= 1 or not 0 <= no <= 1:
            raise ValueError("invalid settlement evidence")
        if exchange_id in self.settled:
            return False
        for key, i in list(self.pending.items()):
            if i.exchange_id == exchange_id:
                self.cancel(key, "settled")
        qty = self.inventory.get(exchange_id, D(0))
        delta = abs(qty) * (yes if qty >= 0 else no)
        self._record(
            "settlement:" + event_id,
            {
                "type": "settlement",
                "exchange_id": exchange_id,
                "cash_delta": str(delta),
                "yes_payout": str(yes),
                "no_payout": str(no),
                "source": source,
            },
        )
        return True

    def on_book(self, book, *, now):
        limits = self.limits
        for i in list(self.pending.values()):
            if (
                Path(limits.kill_file).exists()
                or now >= i.expires
                or now - self.account.received > limits.max_account_age
            ):
                self.cancel(i.key, "killed_or_expired")
                continue
            if book.exchange_id != i.exchange_id or book.tournament != i.tournament:
                continue
            arrival = i.submitted + limits.latency
            if book.received < arrival or now < book.received:
                continue
            if (
                book.source_at is None
                or book.source_at < arrival
                or book.source_at > book.received + 1
                or now - book.received > limits.max_book_age
                or now - book.source_at > limits.max_book_age
                or book.sequence is None
                or book.sequence < i.decision_sequence
            ):
                self.cancel(i.key, "unusable_book")
                continue
            version = (book.exchange_id, book.sequence)
            if version in self.used_versions:
                self.cancel(i.key, "book_liquidity_already_used")
                continue
            remaining, qty, notional = D(i.quantity), D(0), D(0)
            filled_levels = []
            levels = book.offers(i.side) if i.action == "buy" else book.bids_for(i.side)
            for level in levels:
                if (
                    i.action == "buy"
                    and level.price > i.limit
                    or i.action == "sell"
                    and level.price < i.limit
                ):
                    break
                key = (i.exchange_id, i.side, i.action, level.price)
                capacity = (level.quantity * limits.participation).to_integral_value(
                    rounding=ROUND_FLOOR
                )
                take = min(remaining, max(D(0), capacity - self.consumed.get(key, D(0))))
                if take:
                    filled_levels.append({"price": str(level.price), "quantity": str(take)})
                qty += take
                remaining -= take
                notional += take * level.price
                if not remaining:
                    break
            delta = (-notional if i.action == "buy" else notional) - qty * limits.fee_per_share
            self._record(
                "complete:" + i.key,
                {
                    "type": "completed",
                    "key": i.key,
                    "quantity": str(qty),
                    "cash_delta": str(delta),
                    "reason": "ioc_model",
                    "version": book.sequence,
                    "received": book.received,
                    "participation": str(limits.participation),
                    "filled_levels": filled_levels,
                },
            )
