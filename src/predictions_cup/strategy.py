"""Conservative forecast taker, used identically for forward paper and replay."""

import hashlib
from decimal import ROUND_FLOOR, Decimal

from predictions_cup.forecast import estimate_asof
from predictions_cup.paper import Intent


def propose(book, records, mapping, *, now, max_cost=1000, min_edge=0.02, ttl=30):
    """No forecast or unreviewed settlement mapping means no order.

    Uses the lower probability bound at the worst execution price, not average
    cost, and never expands size to consume low-edge marginal levels.
    """
    if (
        max_cost <= 0
        or min_edge < 0
        or ttl <= 0
        or book.sequence is None
        or book.source_at is None
        or not 0 <= now - book.received <= 15
        or not 0 <= now - book.source_at <= 15
        or not mapping
        or not mapping.get("reviewed")
        or mapping.get("status") != "open"
        or now >= mapping["end_at"]
    ):
        return None
    estimate = estimate_asof(
        records,
        exchange_id=book.exchange_id,
        tournament=book.tournament,
        now=now,
        terms_hash=mapping["settlement_sha256"],
    )
    if estimate is None:
        return None
    best = None
    for side, lower in [("YES", estimate["lower"]), ("NO", 1 - estimate["upper"])]:
        levels = book.offers(side)
        acceptable = [x for x in levels if float(x.price) + min_edge <= lower]
        if not acceptable:
            continue
        limit = acceptable[-1].price
        # Historical off-tick price levels may exist; new orders must be on tick.
        limit = (limit / Decimal(".005")).to_integral_value(rounding=ROUND_FLOOR) * Decimal(".005")
        if not Decimal(".005") <= limit <= Decimal(".995"):
            continue
        qty = min(
            int(Decimal(str(max_cost)) / limit),
            int(sum((x.quantity for x in acceptable if x.price <= limit), Decimal(0))),
        )
        if qty <= 0:
            continue
        edge = lower - float(limit)
        candidate = (qty * edge, side, qty, limit)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return None
    _, side, qty, limit = best
    key = hashlib.sha256(
        f"{book.tournament}/{book.exchange_id}/{book.sequence}/{side}".encode()
    ).hexdigest()[:24]
    return Intent(
        key=key,
        tournament=book.tournament,
        exchange_id=book.exchange_id,
        side=side,
        quantity=qty,
        limit=limit,
        submitted=now,
        expires=min(now + ttl, mapping["end_at"]),
        decision_sequence=book.sequence,
    )
