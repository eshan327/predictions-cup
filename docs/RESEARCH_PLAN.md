# Research and trading plan

## Objective, assumptions, and constraints

The 2026 SIG Predictions Cup ranks participants by final SUSQie balance, not Sharpe or average forecasting accuracy. Each binary share settles for 1 or 0; positions on correlated races can lose simultaneously. The 100k starting bankroll is competition currency, not riskless cash. Trading closes November 4, while some markets may not resolve immediately. The platform uses peer-to-peer order matching and can have thin books.

**This project is a research foundation, not an independently validated profitable algorithm.** No backtest or out-of-sample market data has yet established alpha. Do not turn on automated writes until the API schema, authentication, execution rules and cancellation behavior are verified on the live account.

## Architecture (Headlands-inspired)

The attached Max Dama / Headlands article splits systems into market-data normalization, strategy computation, gateway/execution, monitoring, data capture, parameter optimization, backtesting and production reconciliation. This repo follows those boundaries without pretending nanosecond execution matters on a 1-second-batched event market.

1. **Data adapter:** a strictly read-only client and planned version-aware stream; persist raw book snapshots and event timestamps before transforming them. Detect stale snapshots and sequence gaps.
2. **Normalized market layer:** canonical IDs, YES/NO payoff, settlement criteria, actual executable bids and asks, book size and queue. Never equate a displayed probability with a fillable price.
3. **Forecast research:** maintain source, timestamp, methodology, outcome definition and dependency groups. Prefer archived independent forecasts; market-influenced forecasts are not independent evidence.
4. **Opportunity model:** compare conservative probabilities to total sweep cost including depth and estimated fees. Explicitly handle YES/NO complement, mutually exclusive outcomes and implication constraints. Treat related markets as a **joint probability distribution**, not as independent Bernoullis.
5. **Portfolio/risk:** account for existing holdings, balance, reserve, unsettled positions, open orders, sector/party correlation and probability-estimation error. Kelly on a single line is not portfolio sizing. Favor constrained scenario-based optimization; never treat uncertainties from correlated models as independent.
6. **Execution:** initially manual/read-only; future gateway requires idempotent requests, no duplicate retries, a kill switch, max-notional protection, slippage ceilings, cancel/replace logic, and authoritative fill reconciliation.
7. **Research evaluation:** archive point-in-time forecasts. Avoid leakage from revised election model pages. Walk-forward over timestamps, compare to midquote and executable prices, record quote age, available size and settlement rules. Evaluate P&L, log score, Brier, costs, drawdowns and worst correlated scenarios.

## Research schedule

**Phase 1 (implemented foundation):** offline forecast aggregation and a depth-aware scanner; typed quotes, calibration metrics, sample data, CLI, unit tests, CI scaffold. API read adapter includes plausible endpoints but some routes and auth conventions remain unverified.

**Phase 2:** verify Scalar API routes and authentication in the browser; run read-only smoke tests against your account. Persist snapshots with schema validation, paging and rate limits (100 reads/min, 30 writes/min per account; cache 1-2 seconds). Avoid secrets in logs or shell history.

**Phase 3:** add point-in-time race-to-market mapping with exact settlement wording and manually maintained/legally accessible forecast data. Instrument model disagreement; do not scrape behind paywalls or claim forecasts are contemporaneous when they are revised.

**Phase 4:** add correlated joint-outcome simulations based on electoral scenarios and realistic out-of-sample forecast error. Score risk-adjusted and tournament-rank objectives separately. Backtest market-making only with event ordering and queue assumptions that can be defended; no fills from crossed hypothetical snapshots.

**Phase 5:** only after read-only validation, implement guarded paper/live execution with explicit opt-in, order state machine, reconciliation, inventory limits, idempotency and circuit breakers. Use human confirmation initially.

## Current discretionary positions as starting inventory

The user supplied an October 13 portfolio screenshot (NOT wired into trading):

| Position | Shares | Mean paid | Approx capital |
|---|---:|---:|---:|
| Maine Democratic YES | 17,318 | 0.577 | 9,992.49 |
| NY-17 Democratic YES | 12,638 | 0.633 | 7,999.85 |
| Republican Senate NO | 26,548 | 0.565 | 14,999.62 |

Total committed is about 32,991.96 SUSQies. All are directionally exposed to a favorable Democratic election environment. A new allocation engine should ingest actual holdings from account endpoints and *not* assume these are the only positions, that the screenshot is current, or that average cost equals fair probability.

## Security

A secret was shared in conversation. It is **not** stored in this repository. Rotate the original API key through your profile and store the replacement in a secret manager or local env var. The repository is public. Never commit .env, credentials, private portfolio exports or logs containing headers.

## Minimum checklist before live orders

- Verify signed-off official API schema, authorization header, endpoint names and rate limits.
- Confirm contract settlement logic, binary complement behavior and refund rules.
- Integrate account positions/open orders and reconcile snapshots to real fills.
- Use dry-run/paper execution and demonstrate simulator vs exchange behavior.
- Verify maximum exposure after fills and resting orders; make duplicate orders impossible.
- Implement live kill switch and controlled restarts.
- Run tests and track paper performance for enough time to evaluate forecast bias.

## Commands

```bash
python -m pip install -e '.[dev]'
pcup scan examples/sample_snapshot.json
pytest -q
ruff check .
```
