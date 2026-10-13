# Initial empirical audit — 2026-10-13

These are observations from this development session, not a validated trading track record. Private raw responses, source artifacts, timestamps, and paper events are retained outside Git. Run `scripts/research_study.py` against the session database to reproduce the descriptive results. No live order was submitted or cancelled.

## Exchange and account validation

Authenticated reads found 237 tournament markets. All 237 sampled books normalized successfully and were two-sided. The median spread was 0.005 and median best-ask quantity was 2,905. A full sweep required approximately 201 seconds, so it is unsuitable as a simultaneous arbitrage snapshot. Independently refetched paired books were used for the consistency checks below.

The account's three holdings reconciled against exact FIFO lots and complete order/fill history; cash reconstructed from the initial bankroll matched the authoritative balance within the declared rounding tolerance. No real open orders were present. The earlier screenshot arithmetic used rounded average prices and was not used as operational inventory. Personal portfolio exports are not committed.

Captured successful responses were validated against the retrieved official OpenAPI schemas. The local account archive deliberately omits personal profile fields, so it is excluded from whole-profile schema checks.

## Microstructure: do not promote

Six-hour trade windows on Republican Senate control, Democratic NY-17 and Democratic Maine produced 96, 29 and 112 trade records, respectively. The observed YES-price ranges were 0.430–0.440, 0.620–0.635 and 0.565–0.585. Trade-price-change lag-one correlations were approximately −0.288, −0.214 and −0.189. These can be explained by spread bounce and split fills. The tape identifies outcome side, not aggressor direction; treating it as a signed order-flow signal would be a schema error.

Repeated watchlist books produced seven non-overlapping 60-second markouts per held exchange in the initial study. The fixed imbalance-direction diagnostic averaged −0.005 per share after the observed round-trip spread hurdle in each series. There are too few blocks for the configured bootstrap interval, so none is reported. These are price markouts, not executed P&L. The short window gives no positive evidence for an imbalance-taking strategy and cannot determine long-run performance.

Stale last-trade timestamps also did not establish an edge: fresh authoritative books remained available. Last-trade age, book capture age and forecast publication age must remain separate. A large book or a stale display price is not alpha by itself.

## External forecast discrepancies: research candidates

The public Race to the WH Senate widget was observed after its publisher timestamp of October 12, 10:49 p.m. Eastern. Its archived probabilities were Maine Democratic win 0.702 and Republican Senate control 0.276. The first captured books after source availability offered Maine YES at 0.580 and Senate Republican NO at 0.570.

| Outcome purchased | Source probability | Ask | Edge after 5pp haircut | After 10pp | After 15pp |
|---|---:|---:|---:|---:|---:|
| Maine Democratic YES | 0.702 | 0.580 | 0.072 | 0.022 | −0.028 |
| Republican Senate NO | 0.724 | 0.570 | 0.104 | 0.054 | 0.004 |

Haircuts are sensitivity assumptions, not empirically calibrated uncertainty intervals. At the 15-point setting neither clears the strategy's 0.02 minimum edge. At 10 points, both appear attractive before depth, definition and portfolio checks. Senate-control caucus/independent/fallback semantics still need stronger source alignment. No NY-17 probability was invented from the Senate feed. No present-day forecast was backfilled into historical decisions.

RTWH describes polling, fundamentals, candidate quality and fundraising inputs. Multiple election models may share those inputs. This session did not establish independence, obtain a historical first-publication archive, or fit calibration on prior elections. Default checked-in forecasts remain empty.

## Cross-contract consistency: narrow conditional opportunities

Fresh paired books on the separate Democratic and Republican winner contracts showed:

| Race | Cost of 100 NO shares on each party | Minimum normal-outcome payout | Conditional gross difference |
|---|---:|---:|---:|
| Maine Senate | 99.50 | 100 | +0.50 |
| NY-17 House | 99.50 | 100 | +0.50 |
| Senate chamber control | 100.50 | 100 | −0.50 |

The Maine and NY-17 node trees matched on race ID, stage ID, date and party-winner resolution type, with different party winners. Mutual exclusion supports at least one NO payout; it does not require Democrats/Republicans to exhaust all winners. The bound is contingent on unchanged normal settlement terms, fills on every leg, and costs. A 0.0025 per-share cost on each leg removes the observed 0.005 pair edge. Availability can disappear between reads.

The existing YES positions also prevent blindly adding opposite-side NO inventory on the same exchange; switching or closing positions has its own spread and execution costs. The canonical relationship graph returned no rows, so this was a reviewed semantic check, not a claimed engine relationship guarantee.

The API documents an all-or-none multi-leg mode, but its actual behavior was not exercised. A batch of individually accepted orders is not an all-leg fill guarantee. No basket strategy is enabled automatically.

## Bounded forward paper experiment

A separate, private experiment used the verified Maine party-winner mapping, the archived RTWH probability, a declared 10-point uncertainty haircut and a **1,000 maximum added-cost cap**. The first cycle proposed 1,724 YES shares with a 0.580 limit. A subsequent observed book, after latency, modeled an IOC fill of all 1,724 shares for 999.92. The next proposal was rejected by the aggregate cost cap. The paper log was reloaded and its cash/inventory agreed. There were no pending orders when the experiment ended.

This tests the connected collection → reconciliation → as-of forecast → decision → limit checks → later-book model → durable accounting workflow. It does not establish that SIG would have filled the order, that the forecast is calibrated, or that holding the contract is profitable. The market has not settled. Private paper inventory is separate from the unchanged exchange account.

## Decisions

Keep live execution unavailable. Keep passive filling unavailable. Retain the imbalance diagnostic as a control, not an active signal. Continue collecting before tuning. Prioritize exact cross-contract bounds and independently corroborated external forecast differences, with a joint portfolio model and conservative cost/latency sensitivity. A convincing edge requires longer forward observations and settled, temporally valid evaluation—not more speculative features.
