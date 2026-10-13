"""Authoritative REST collection and conservative account reconciliation."""

import hashlib
import json
import time
from collections import defaultdict
from decimal import Decimal

from predictions_cup.models import AccountState, Holding, normalize_book, timestamp


def D(x):
    return Decimal(str(x))


def reconcile(
    tournament, cash, positions, orders, fills, *, initial_balance, received, history_complete=True
):
    issues = []
    holdings = []
    ids = set()
    for p in positions["positions"]:
        eid = str(p["exchangeId"])
        if eid in ids:
            issues.append("duplicate holding")
        ids.add(eid)
        quantity = D(p["quantity"])
        lots = p["lots"]
        lot_qty = sum((D(x["quantity"]) * (1 if x["side"] == "YES" else -1) for x in lots), D(0))
        lot_cost = sum((D(x["quantity"]) * D(x["entryPrice"]) for x in lots), D(0))
        if quantity != lot_qty or abs(lot_cost - D(p["costBasis"])) > D(".02"):
            issues.append(f"lot mismatch: {eid}")
        holdings.append(
            Holding(
                exchange_id=eid,
                quantity=quantity,
                cost_basis=D(p["costBasis"]),
                market_value=D(p["marketValue"]),
            )
        )
    order_map = {str(o["id"]): o for o in orders}
    if len(order_map) != len(orders):
        issues.append("duplicate orders")
    reserved = D(0)
    for o in orders:
        if o["tournamentId"] != tournament:
            issues.append("order scope mismatch")
        if o["open"] and o["action"] == "buy":
            reserved += D(o["quantity"]) * (
                D(o["priceLimit"]) if o["priceLimit"] is not None else D(1)
            )
    if not history_complete:
        issues.append("incomplete history")
    # Fills alone omit action: join to the authoritative order, never infer it from sign.
    reconstructed = defaultdict(Decimal)
    reconstructed_cash = D(initial_balance)
    seen = set()
    for f in fills:
        key = (f["id"], f["orderId"], f["filledAt"])
        if key in seen:
            issues.append("duplicate fill")
            continue
        seen.add(key)
        o = order_map.get(str(f["orderId"]))
        if o is None or f["price"] is None:
            issues.append("fill lacks order or price")
            continue
        if o["side"] != f["side"] or str(o["exchangeId"]) != str(f["exchangeId"]):
            issues.append("fill/order mismatch")
        qty = D(f["quantity"])
        if (qty > 0) != (f["side"] == "yes"):
            issues.append("fill side/sign mismatch")
        action = 1 if o["action"] == "buy" else -1
        reconstructed[str(f["exchangeId"])] += qty * action
        reconstructed_cash -= abs(qty) * D(f["price"]) * action
    actual = {h.exchange_id: h.quantity for h in holdings if h.quantity}
    reconstructed = {k: v for k, v in reconstructed.items() if v}
    if actual != reconstructed:
        issues.append("fill inventory differs; check settlements or incomplete history")
    if abs(D(cash) - reconstructed_cash) > D(".02"):
        issues.append("cash ledger differs; check fees, settlements, deposits or collateral")
    summary = positions["summary"]
    if abs(sum((h.cost_basis for h in holdings), D(0)) - D(summary["totalCostBasis"])) > D(".02"):
        issues.append("position summary mismatch")
    return AccountState(
        tournament=tournament,
        received=received,
        cash=D(cash),
        reserved_buys=reserved,
        holdings=tuple(holdings),
        open_order_count=sum(bool(o["open"]) for o in orders),
        reconciled=not issues,
        issues=tuple(sorted(set(issues))),
    )


def collect(client, store, slug, *, exchange_ids=(), all_books=False):
    started = time.time()
    tournament = client.get(f"/tournaments/{slug}")
    tid = tournament["id"]
    params = {"tournamentId": tid}
    cash_before = client.get("/account", params=params)["balance"]
    positions = client.get(f"/tournaments/{slug}/portfolio/positions")
    orders = client.rows("/orders", params={**params, "status": "all", "limit": 200})
    fills = client.rows(f"/tournaments/{slug}/portfolio/fills", params={"limit": 200})
    # Do not make up ledger semantics for settlements/collateral. Capture them and
    # block paper seeding until explicitly supported by reconciliation.
    settlements = client.rows(f"/tournaments/{slug}/portfolio/settlements", params={"limit": 200})
    open_after = client.rows("/orders", params={**params, "status": "open", "limit": 200})
    cash_after = client.get("/account", params=params)["balance"]
    positions_after = client.get(f"/tournaments/{slug}/portfolio/positions")

    def inventory_signature(payload):
        return sorted(
            (p["exchangeId"], p["quantity"], p["costBasis"]) for p in payload["positions"]
        )

    def open_signature(rows):
        return sorted(
            (str(o["id"]), o["quantity"], o["priceLimit"], o["side"], o["action"])
            for o in rows
            if o["open"]
        )

    stable = (
        cash_before == cash_after
        and inventory_signature(positions) == inventory_signature(positions_after)
        and open_signature(orders) == open_signature(open_after)
    )
    account = reconcile(
        tid,
        cash_after,
        positions_after,
        orders,
        fills,
        initial_balance=tournament["initialBalance"],
        received=time.time(),
        history_complete=stable and not settlements,
    )
    markets = client.rows(f"/tournaments/{slug}/markets", params={"limit": 100})
    eligible = {str(e["id"]) for m in markets if m["status"] == "open" for e in m["exchanges"]}
    selected = (
        eligible
        if all_books
        else set(exchange_ids) | {h.exchange_id for h in account.holdings if h.quantity}
    )
    if not selected.issubset(eligible):
        raise ValueError("requested/held exchange not in open tournament markets")
    mappings = {}
    # Only watched markets need repeated resolution metadata; a universe sweep
    # remains a descriptive scan, not a synchronous trading snapshot.
    if not all_books:
        for market in markets:
            watched = [str(e["id"]) for e in market["exchanges"] if str(e["id"]) in selected]
            if watched:
                nodes = client.get(f"/markets/{market['id']}/nodes", params=params)
                digest = hashlib.sha256(
                    json.dumps(nodes["root"], sort_keys=True).encode()
                ).hexdigest()
                for eid in watched:
                    mappings[eid] = {
                        "settlement_sha256": digest,
                        "status": market["status"],
                        "end_at": min(
                            timestamp(market["settlementDate"]), timestamp(tournament["endDate"])
                        ),
                        "observed_at": time.time(),
                        "market_id": market["id"],
                    }
    books, failures = [], []
    for eid in sorted(selected):
        try:
            raw = client.get_orderbook(eid, tid)
            book = normalize_book(raw, tid, time.time())
            if book.exchange_id != eid:
                raise ValueError("book exchange mismatch")
            store.add_book(book)
            books.append(book)
        except (ValueError, KeyError) as exc:
            failures.append({"exchange": eid, "error": type(exc).__name__})
    result = {
        "started": started,
        "ended": time.time(),
        "tournament": tid,
        "slug": slug,
        "status": tournament["status"],
        "end_at": timestamp(tournament["endDate"]),
        "markets": len(markets),
        "book_count": len(books),
        "book_errors": failures,
        "mappings": mappings,
        "account": account.model_dump(mode="json"),
    }
    status = "ok" if account.reconciled and not failures else "blocked"
    store.run(time.time(), status, result)
    return result


def backfill(client, store, slug, exchange_ids, start, end):
    """Fixed time window makes reverse cursor traversal reproducible."""
    tid = client.get(f"/tournaments/{slug}")["id"]
    if timestamp(start) >= timestamp(end):
        raise ValueError("empty history window")
    result = {}
    for eid in exchange_ids:
        rows = client.rows(
            f"/exchanges/{eid}/trades",
            params={"tournamentId": tid, "from": start, "to": end, "limit": 200},
        )
        keys = {(r["id"], r["createdAt"]) for r in rows}
        if len(keys) != len(rows):
            raise ValueError("duplicate trades across pages")
        result[eid] = len(rows)
    return result
