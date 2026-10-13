# Research plan and architecture

The initial PR was a useful synthetic demonstration. It had unverified routes, no persistent observations, no authoritative portfolio reconstruction and no execution evidence. The new system separates those concerns and retains the older scanner only as an offline example.

The [Headlands article by Max Dama](https://blog.headlandstech.com/2017/08/03/quantitative-trading-summary/) motivates normalization, decision logic, execution, capture, monitoring and reconciliation. Here these are modules in one Python process backed by SQLite, not an HFT deployment. Co-location, nanosecond signals, distributed buses and a complex service hierarchy are unjustified for this exchange and task.

## Promotion sequence

1. **Capture and reconcile — implemented and exercised.** Authenticated GETs, explicit tournament scope, complete pagination, durable raw responses, normalized books, and account/lot/fill/order/cash checks. Retain immutable observations and fail closed on schema or accounting ambiguity.
2. **Verify outcomes — implemented for watched markets.** Archive official node trees and compare their hashes before each paper cycle. Do not infer mutually exclusive/exhaustive relationships from similar titles. The observed canonical relationship graph was empty.
3. **Research economic edge — exploratory, not validated.** Compare archived external probabilities to available prices/depth. Check payoff bounds across exactly matched contracts. Study stale prices using source observation time and later executable quotes. Book imbalance is only a benchmark pending positive spread-adjusted forward evidence.
4. **Paper operation — implemented and exercised.** Conservative delayed IOC model, replay, durable inventory, reservations, duplicate/concurrent-writer protections, cash and exposure caps, lifecycle checks, explicit payouts and kill switch. Passive quoting remains disabled because queue evidence is missing.
5. **Calibrate and validate — tools implemented, evidence insufficient.** Accumulate multiple days, market regimes and historical election cycles with first-publication snapshots. Evaluate Brier/log loss by settled event; compare to market baselines; cluster correlated races/election cycles. Select parameters only on past data. Report cost/latency/depth sensitivity, drawdowns and conditional capacity. Never describe a short paper run as out-of-sample alpha.
6. **Portfolio and tournament decisions — research tools implemented.** Joint scenarios include existing positions and adverse common-party outcomes. Compare expected wealth, log wealth and prize utility under several explicit opponent assumptions. Avoid independently sizing correlated races or disguising arbitrary correlations as estimates.
7. **Live execution — intentionally unavailable.** Requires a separately authorized gateway and actual tests of order lifecycle, all-or-none execution, expiries, conflicts, fills, refunds/settlements and idempotent recovery. A trade-enabled key does not authorize this step.

## Priorities from current evidence

First, investigate the narrow cross-contract inequalities with fresh paired books, exact payoff definitions, account-compatible entry/unwind and full execution costs. Second, compare more independent forecast sources and historical calibration; RTWH is a useful input but shared polling inputs limit ensemble diversification. Third, retain order-book diagnostics as a negative/control benchmark, not a promoted signal. Market-making needs event/queue data and adverse-selection measurements before it can produce meaningful fills.

There is no validated edge switch to flip today. The deliverable is an operational research/paper system with explicit evidence gates, not a promise to win the tournament. See `RESEARCH_FINDINGS.md` for the actual measurements and unresolved assumptions.
