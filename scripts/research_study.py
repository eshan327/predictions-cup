"""Reproduce diagnostics and external-forecast sensitivity from private captures.

No current forecast is joined to earlier prices. This is a descriptive study,
not a profitability estimate, calibration study, or out-of-sample backtest.
"""

import argparse
import json

from predictions_cup.evaluation import report
from predictions_cup.external import parse_rtwh
from predictions_cup.models import Book, timestamp
from predictions_cup.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
args = parser.parse_args()
with Store(args.db) as store:
    result = report(store)
    rows = store.db.execute(
        "SELECT * FROM observations WHERE path='/external/rtwh/senate' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    comparisons = []
    if rows:
        row = rows[0]
        source = parse_rtwh(json.loads(row["body"]), timestamp(row["received"]))
        # These two identities were examined against /markets/{id}/nodes.
        # Senate aggregate caucus definitions remain a mapping uncertainty.
        for eid, key, side in [("959", "Maine/D", "YES"), ("843", "Senate/R", "NO")]:
            raw = store.db.execute(
                "SELECT body FROM books WHERE exchange_id=? AND received>=? "
                "ORDER BY received LIMIT 1",
                (eid, source["observed_at"]),
            ).fetchone()
            if raw is None:
                continue
            b = Book.model_validate_json(raw["body"])
            p = source["probabilities"][key]
            offers = b.offers(side)
            if not offers:
                continue
            fair = p if side == "YES" else 1 - p
            ask = float(offers[0].price)
            comparisons.append(
                {
                    "exchange": eid,
                    "side": side,
                    "source_probability": fair,
                    "source_published": source["published_at"],
                    "source_observed": source["observed_at"],
                    "book_received": b.received,
                    "best_ask": ask,
                    "displayed_quantity": str(offers[0].quantity),
                    "haircut_sensitivity": {str(h): fair - h - ask for h in [0.05, 0.10, 0.15]},
                    "bounds_are_calibrated": False,
                }
            )
    result["external_comparisons"] = comparisons
    print(json.dumps(result, indent=2))
