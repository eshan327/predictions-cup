# Predictions Cup

Quantitative, research-first tooling for SIG's 2026 prediction-market tournament.

**Status: research prototype, not a validated profitable strategy and not a live trading bot.** No automatic orders can be submitted from this repository. This is deliberate: the API's interactive Scalar reference must be verified against actual authenticated responses before safe execution is possible.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pcup scan examples/sample_snapshot.json
pytest -q
ruff check .
```

The sample contract and forecasts are entirely synthetic. The scanner computes model fair probability, group-aware forecast blending, uncertainty haircuts, order-book depth-aware average prices, and ranked trade opportunities. A strong apparent edge is **not** sufficient evidence to trade.

## Structure

- `src/predictions_cup/research.py`: log-odds forecast blending, executable book sweeps, edge scanning, calibration scores, single-bet fractional Kelly (diagnostic only).
- `src/predictions_cup/portfolio.py`: existing inventory, joint-outcome scenario P&L, tail loss, a conservative new-capital budget and implication constraints.
- `src/predictions_cup/api.py`: read-only API HTTP adapter, with candidate endpoint routes and tentative auth scheme requiring verification; no order submission code.
- `src/predictions_cup/cli.py`: offline JSON scanner.
- `examples/`: synthetic input fixture.
- `tests/`: deterministic unit tests.
- `docs/RESEARCH_PLAN.md`: Headlands-inspired trading-system architecture and production roadmap.

## SIG API

See [the official Scalar reference](https://sig.thesuper.market/api/v1/docs) and [product guide](https://sig.thesuper.market/docs). Participant automation is permitted. Confirmed platform constraints: 100 read / 30 write requests per minute per account, exchanges/prices bulk endpoint with up to 100 IDs, market data caching of 1–2 seconds, and tournament market streams. Exact schemas, paginated fields, book structure, auth format and websocket setup **must** be verified before proceeding. This repo does not claim successful SIG authentication.

## Immediate priorities

1. **Rotate the API key posted in the chat.** Never share a replacement in a commit or issue.
2. Verify live API schema and authentication with read-only calls. Compare raw API data with the web UI, including cash, orders, held inventory, and market settlement criteria.
3. Archive point-in-time prices/orderbooks, forecast revisions and actual fills. Avoid hindsight and dependent-model circularity.
4. Extend scenario risk to correlated race outcomes, market constraints and competition-level rank objectives; evaluate offline with historical data.
5. Add paper-trading reconciliation; only then consider separately authorized, gated execution.

Your initial portfolio screenshot reflects approximately 33% deployed, with all three lines directionally correlated. Refer to [the research plan](docs/RESEARCH_PLAN.md) for the position breakdown and risk considerations.

## Security

This is a public GitHub repository. `.env`, private data, and reports are ignored. The key provided in conversation is **not committed or used** by this repo. Secrets belong in your local environment or a proper secrets manager.
