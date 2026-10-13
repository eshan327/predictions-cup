"""Reproducible diagnostics. Tape statistics are never presented as fill backtests."""

import json
from collections import defaultdict

import numpy as np

from predictions_cup.models import Book, timestamp


def book_features(book):
    if not book.bids or not book.asks:
        return None
    bid, ask = book.bids[0], book.asks[0]
    b, a, bq, aq = map(float, (bid.price, ask.price, bid.quantity, ask.quantity))
    return {
        "mid": (b + a) / 2,
        "spread": a - b,
        "imbalance": (bq - aq) / (bq + aq),
        "microprice": (a * bq + b * aq) / (bq + aq),
        "bid_qty": bq,
        "ask_qty": aq,
    }


def purged_splits(times, label_end, *, folds=3, min_train=20):
    """Expanding temporal folds; exclude training labels overlapping validation."""
    t, end = np.asarray(times), np.asarray(label_end)
    if (
        len(t) != len(end)
        or len(t) <= min_train
        or folds < 1
        or np.any(np.diff(t) < 0)
        or np.any(end < t)
    ):
        raise ValueError("invalid temporal sample")
    for test in np.array_split(np.arange(min_train, len(t)), folds):
        if not len(test):
            continue
        train = np.flatnonzero((t < t[test[0]]) & (end < t[test[0]]))
        if len(train) >= min_train:
            yield train, test


def block_mean_interval(values, *, block=10, samples=2000, seed=7):
    """Moving-block bootstrap interval; dependence assumption must be reported."""
    x = np.asarray(values, float)
    if x.ndim != 1 or len(x) < 2 * block or block < 1 or samples < 1 or not np.all(np.isfinite(x)):
        raise ValueError("insufficient finite observations for chosen block")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(x) - block + 1, size=(samples, int(np.ceil(len(x) / block))))
    indices = (starts[..., None] + np.arange(block)).reshape(samples, -1)[:, : len(x)]
    lo, hi = np.quantile(x[indices].mean(axis=1), [0.025, 0.975])
    return {
        "mean": float(x.mean()),
        "lower": float(lo),
        "upper": float(hi),
        "block": block,
        "samples": len(x),
    }


def book_signal_test(books, *, horizon=60, max_label_delay=30):
    """Non-overlapping forward mid marks for fixed, unfitted pressure signal.

    Returns a signal diagnostic only. Spread costs included as a round-trip
    hurdle; neither side is assumed filled. No last-observation carry-forward.
    """
    rows = sorted(books, key=lambda b: b.received)
    values = []
    next_start = float("-inf")
    for i, b in enumerate(rows):
        if b.received < next_start:
            continue
        f = book_features(b)
        if f is None or b.source_at is None or b.received - b.source_at > 15:
            continue
        future = next((x for x in rows[i + 1 :] if x.received >= b.received + horizon), None)
        if future is None or future.received > b.received + horizon + max_label_delay:
            continue
        g = book_features(future)
        if g is None or future.source_at is None or future.received - future.source_at > 15:
            continue
        direction = np.sign(f["imbalance"])
        values.append(direction * (g["mid"] - f["mid"]) - (f["spread"] + g["spread"]) / 2)
        next_start = future.received
    return {
        "observations": len(values),
        "horizon_seconds": horizon,
        "mean_spread_adjusted_markout": float(np.mean(values)) if values else None,
        "interval": block_mean_interval(values) if len(values) >= 20 else None,
        "validated_edge": False,
        "kind": "markout_diagnostic_not_fills",
    }


def tape_report(rows):
    unique = {(r["id"], r["createdAt"]): r for r in rows}
    rows = sorted(unique.values(), key=lambda r: (timestamp(r["createdAt"]), r["id"]))
    valid = [r for r in rows if r["price"] is not None]
    prices = np.array([r["price"] for r in valid], float)
    times = np.array([timestamp(r["createdAt"]) for r in valid])
    delta = np.diff(prices)
    varying = len(delta) > 2 and np.std(delta[:-1]) > 0 and np.std(delta[1:]) > 0
    return {
        "trades": len(rows),
        "priced_trades": len(valid),
        "quantity": sum(r["size"] for r in rows),
        "first": rows[0]["createdAt"] if rows else None,
        "last": rows[-1]["createdAt"] if rows else None,
        "median_gap_seconds": float(np.median(np.diff(times))) if len(times) > 1 else None,
        "min_price": float(prices.min()) if len(prices) else None,
        "max_price": float(prices.max()) if len(prices) else None,
        "lag1_price_change_correlation": float(np.corrcoef(delta[:-1], delta[1:])[0, 1])
        if varying
        else None,
        "warning": "Side is outcome, not aggressor. Trade prices can bounce across the spread.",
    }


def report(store):
    books = defaultdict(list)
    for r in store.db.execute("SELECT body FROM books ORDER BY received,id"):
        b = Book.model_validate_json(r["body"])
        books[(b.tournament, b.exchange_id)].append(b)
    latest = {key: vals[-1] for key, vals in books.items()}
    feats = [f for b in latest.values() if (f := book_features(b)) is not None]
    tapes = defaultdict(list)
    for r in store.db.execute(
        "SELECT path,params,body FROM observations WHERE path LIKE '%/trades'"
    ):
        params, body = json.loads(r["params"]), json.loads(r["body"])
        tapes[(params["tournamentId"], str(body["exchangeId"]))].extend(body["data"])
    return {
        "kind": "descriptive_audit_not_profitability_evidence",
        "books": sum(map(len, books.values())),
        "exchanges": len(books),
        "two_sided_books": len(feats),
        "median_spread": float(np.median([f["spread"] for f in feats])) if feats else None,
        "median_best_ask_quantity": float(np.median([f["ask_qty"] for f in feats]))
        if feats
        else None,
        "markouts": {f"{t}/{e}": book_signal_test(v) for (t, e), v in books.items() if len(v) > 1},
        "tape": {f"{t}/{e}": tape_report(v) for (t, e), v in tapes.items()},
    }


def consistency_cost(books, legs, *, quantity, minimum_payout, now, max_age=15, fee=0):
    """Price an explicitly verified payoff basket; never infer relations from titles.

    No atomic fill guarantee. Returning a positive bound is only a candidate.
    """
    if quantity <= 0 or minimum_payout < 0 or fee < 0 or not legs:
        raise ValueError("invalid basket")
    if len({eid for eid, _ in legs}) != len(legs):
        raise ValueError("duplicate legs would double-count book depth")
    total = 0.0
    scopes = set()
    for eid, side in legs:
        b = books[eid]
        scopes.add(b.tournament)
        if (
            not 0 <= now - b.received <= max_age
            or b.source_at is None
            or not 0 <= now - b.source_at <= max_age
        ):
            return None
        remain, cost = quantity, 0.0
        for level in b.offers(side):
            take = min(remain, float(level.quantity))
            cost += take * (float(level.price) + fee)
            remain -= take
            if remain == 0:
                break
        if remain:
            return None
        total += cost
    if len(scopes) != 1:
        raise ValueError("mixed tournament basket")
    return {
        "cost": total,
        "minimum_profit_if_all_legs_fill": quantity * minimum_payout - total,
        "atomic_fill_verified": False,
    }
