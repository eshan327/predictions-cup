"""Small offline research CLI; intentionally no --trade command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from predictions_cup.research import (
    Forecast,
    Level,
    blend_forecasts,
    scan_yes_no,
)


def analyze(path: Path) -> None:
    payload = json.loads(path.read_text())
    result = []
    for market in payload["markets"]:
        fs = [Forecast(**f) for f in market["forecasts"]]
        est = blend_forecasts(fs)
        opportunities = scan_yes_no(
            [Level(**x) for x in market["yes_asks"]],
            [Level(**x) for x in market["no_asks"]],
            est,
            max_qty=market.get("max_qty", 1000),
            max_cost=market.get("max_cost", 2000),
        )
        best = opportunities[:3]
        result.append(
            {
                "market": market["market"],
                "fair_probability": round(est.fair_probability, 4),
                "uncertainty": round(est.uncertainty, 4),
                "opportunities": [
                    {
                        "side": x.side,
                        "quantity": x.quantity,
                        "average_cost": round(x.quote.avg_price, 4),
                        "expected_pnl": round(x.expected_pnl, 2),
                        "conservative_edge": round(x.conservative_edge, 4),
                    }
                    for x in best
                ],
            }
        )
    print(json.dumps(result, indent=2))


def main() -> None:
    import time

    from predictions_cup.api import SIGClient
    from predictions_cup.collection import backfill, collect
    from predictions_cup.evaluation import report
    from predictions_cup.forecast import ForecastRecord
    from predictions_cup.operations import health, paper_cycle
    from predictions_cup.paper import Limits
    from predictions_cup.replay import replay
    from predictions_cup.store import Store

    parser = argparse.ArgumentParser(description="SIG research and paper trading; no live writes")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Legacy synthetic offline example")
    scan.add_argument("path", type=Path)
    for name in ("collect", "backfill", "report", "health", "paper", "replay", "external"):
        p = sub.add_parser(name)
        p.add_argument("--db", type=Path, default=Path("data/private/research.sqlite"))
        if name in ("collect", "backfill", "paper"):
            p.add_argument("--slug", default="midterm-elections")
        if name in ("collect", "backfill"):
            p.add_argument("--exchange", action="append", default=[])
        if name == "collect":
            p.add_argument("--all-books", action="store_true")
        if name in ("collect", "paper"):
            p.add_argument("--cycles", type=int, default=1, help="0 means run until interrupted")
            p.add_argument("--interval", type=float, default=10 if name == "paper" else 60)
        if name == "backfill":
            p.add_argument("--start", required=True)
            p.add_argument("--end", required=True)
        if name in ("paper", "replay"):
            p.add_argument("--forecasts", type=Path, required=True)
            p.add_argument("--mappings", type=Path, required=True)
            p.add_argument("--limits", type=Path)
            p.add_argument("--paper-db", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "scan":
        analyze(args.path)
        return
    if args.command in ("paper", "replay"):
        records = [
            ForecastRecord.model_validate_json(line)
            for line in args.forecasts.read_text().splitlines()
            if line.strip()
        ]
        mappings = json.loads(args.mappings.read_text())
        limits = Limits.model_validate_json(args.limits.read_text()) if args.limits else Limits()
        if args.paper_db.resolve() == args.db.resolve():
            parser.error("paper and research databases must differ")
    with Store(args.db) as store:
        if args.command == "external":
            from predictions_cup.external import fetch_rtwh

            result = fetch_rtwh(store)
        elif args.command == "report":
            result = report(store)
        elif args.command == "health":
            result = health(store)
            print(json.dumps(result, indent=2))
            raise SystemExit(0 if result["healthy"] else 2)
        elif args.command == "replay":
            result = replay(store, args.paper_db, records, mappings, limits=limits)
        else:
            if args.command in ("collect", "paper") and (args.cycles < 0 or args.interval < 10):
                parser.error("cycles must be nonnegative; interval must be at least 10 seconds")
            with SIGClient(capture=store.capture) as client:
                if args.command == "backfill":
                    if not args.exchange:
                        parser.error("backfill requires at least one --exchange")
                    result = backfill(client, store, args.slug, args.exchange, args.start, args.end)
                else:
                    cycle = 0
                    while args.cycles == 0 or cycle < args.cycles:
                        try:
                            if args.command == "collect":
                                result = collect(
                                    client,
                                    store,
                                    args.slug,
                                    exchange_ids=args.exchange,
                                    all_books=args.all_books,
                                )
                            else:
                                with Store(args.paper_db) as paper_store:
                                    result = paper_cycle(
                                        client,
                                        store,
                                        paper_store,
                                        args.slug,
                                        records,
                                        mappings,
                                        limits=limits,
                                    )
                            print(json.dumps(result, indent=2), flush=True)
                        except Exception as exc:
                            store.run(time.time(), "error", {"error_type": type(exc).__name__})
                            raise SystemExit(
                                "Collection/paper halted: " + type(exc).__name__
                            ) from None
                        cycle += 1
                        if args.cycles == 0 or cycle < args.cycles:
                            time.sleep(args.interval)
                    return
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
