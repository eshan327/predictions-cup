"""Small offline research CLI; intentionally no --trade command."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from predictions_cup.research import (
    Forecast, Level, blend_forecasts, scan_yes_no,
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
        result.append({
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
                } for x in best
            ],
        })
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Predictions Cup research tools")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Score an offline JSON snapshot; NO trading")
    scan.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "scan":
        analyze(args.path)


if __name__ == "__main__":
    main()
