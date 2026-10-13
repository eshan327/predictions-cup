"""Validated normalized state. Money uses Decimal; timestamps use UTC epoch seconds."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")


class BookLevel(Model):
    price: Decimal = Field(ge=0, le=1)
    quantity: Decimal = Field(gt=0)


class Book(Model):
    tournament: str
    exchange_id: str
    market_id: str
    received: float
    source_at: float | None
    sequence: int | None = Field(ge=0)
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

    @model_validator(mode="after")
    def ordered(self):
        for levels, reverse in ((self.bids, True), (self.asks, False)):
            prices = [x.price for x in levels]
            if prices != sorted(set(prices), reverse=reverse):
                raise ValueError("book levels must be unique and ordered")
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise ValueError("locked/crossed book; resync before research")
        return self

    def offers(self, side: Literal["YES", "NO"]):
        if side == "YES":
            return self.asks
        if side != "NO":
            raise ValueError("unknown side")
        return tuple(BookLevel(price=1 - x.price, quantity=x.quantity) for x in self.bids)

    def bids_for(self, side):
        if side == "YES":
            return self.bids
        if side != "NO":
            raise ValueError("unknown side")
        return tuple(BookLevel(price=1 - x.price, quantity=x.quantity) for x in self.asks)


class Holding(Model):
    exchange_id: str
    quantity: Decimal
    cost_basis: Decimal = Field(ge=0)
    market_value: Decimal = Field(ge=0)


class AccountState(Model):
    tournament: str
    received: float
    cash: Decimal
    reserved_buys: Decimal = Field(ge=0)
    holdings: tuple[Holding, ...]
    open_order_count: int = Field(default=0, ge=0)
    reconciled: bool
    issues: tuple[str, ...]

    @property
    def spendable(self):
        return max(Decimal(0), self.cash - self.reserved_buys)


def timestamp(value):
    from datetime import datetime

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.timestamp()


def normalize_book(raw, tournament, received):
    version = raw["asOf"]
    book = Book(
        tournament=tournament,
        exchange_id=str(raw["exchangeId"]),
        market_id=str(raw["marketId"]),
        received=received,
        sequence=version["sequence"] if version else None,
        source_at=timestamp(version["at"]) if version else None,
        bids=raw["bids"],
        asks=raw["asks"],
    )
    for field, levels in [("bestBid", book.bids), ("bestAsk", book.asks)]:
        expected = levels[0].price if levels else None
        actual = Decimal(str(raw[field])) if raw[field] is not None else None
        if expected != actual:
            raise ValueError("best price disagrees with depth")
    return book
