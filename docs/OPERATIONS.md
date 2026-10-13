# Research and paper runbook

## State and recovery

Keep all financial captures under ignored `data/private/`. SQLite WAL stores each raw successful response before parsing. A failed cycle records a failed heartbeat and stops continuous mode. It does not make an earlier successful snapshot look current. `pcup health` checks collection age, account age, status, and the STOP file. It is a local check, not an external alerting service; use its exit status in your host's monitoring.

The paper event log persists its authoritative account seed, limits, intents, fills/cancellations, and settlement credits. On restart it rebuilds state exactly. Changed limits require a fresh paper database. Concurrent paper writers are rejected using a transactional event revision check. A changed real-account cash/holding/order signature requires fresh reconciliation and a new paper seed; this prevents double-counting discretionary activity.

Reconciliation covers complete fills joined to orders, signed inventory, FIFO lots, cost basis and cash from the initial balance. It currently fails closed after historical settlements, fees, collateral or deposits that cannot be explained by the fill ledger. Those endpoints are captured where supported, but automatic ledger treatment is not invented. `PaperBroker.settle` accepts explicit authoritative payouts for both outcomes; it never assumes a refund is 0.5. Live settlement reconciliation needs additional actual examples before promotion.

## Forecast and settlement inputs

`pcup external` captures the public RTWH Senate widget data without sending SIG credentials to it. The parser matches table headers, not fixed row positions, validates percentages and the publisher update time, and refuses a changed/stale/future-dated source. Its embedded data URL was discovered from the publisher's public widget. It may change; a failure requires inspecting the source, not guessing a new schema.

A JSONL forecast record contains:

```json
{"exchange_id":"EXCHANGE_ID","tournament":"TOURNAMENT_UUID","source":"model-name","source_url":"https://publisher.example/forecast","dependency_group":"shared-poll-model","published_at":1791859740,"observed_at":1791868609,"expires_at":1791955009,"probability":0.70,"lower":0.55,"upper":0.85,"settlement_sha256":"64-character-sha256","artifact_sha256":"64-character-sha256","kind":"model","reviewed":false}
```

The example hash placeholders are intentionally invalid. Use the captured source hash and the SHA-256 of `json.dumps(nodes['root'], sort_keys=True).encode()` for actual inputs. Collection results contain the latter under `mappings`. Times are UTC epoch seconds. Keep reviewed records in private data, not public configuration. Publisher time and first-observed time are distinct; never backdate the latter. Forecast revisions from the same source replace earlier ones as of their observed time. Shared dependency groups receive one vote; uncertainty uses the envelope across sources, not an independence-based standard-error reduction.

`lower`/`upper` are declared sensitivity bounds, **not confidence intervals** unless independently calibrated. A qualitative race rating is not a numeric probability. Forecast import does not automatically approve it for paper decisions.

The mapping JSON is keyed by exchange ID:

```json
{"EXCHANGE_ID":{"reviewed":false,"observed_at":1791868609,"settlement_sha256":"64-character-sha256","status":"open","end_at":1793811600}}
```

Review event identity, party/candidate, primary/general/runoff, chamber tie-break/caucus rules, deadline, void/refund treatment, and source definition. Mark reviewed only after that check. Each forward paper cycle compares the mapping hash to freshly fetched official nodes. Changed or unverified terms cancel pending intents. Source artifacts should be retained alongside the records for audit.

## Execution model and limits

The default system holds at least 50,000 cash, allows at most 1,000 new cost per order and 5,000 total added cost, and does not use collateral or naked shorts. These are conservative operational caps, not optimized competition allocations. Existing holdings are included by seeding from reconciled inventory/cash. Same-exchange opposite-side buys are rejected until the existing side is explicitly closed.

An IOC paper order can use only a subsequent book whose source capture time is after submission plus 2 seconds. It respects its limit, age, expiry, tournament, quantity and 25% displayed-depth participation. Partial fills cancel the remainder. Already-used engine versions cannot fill again. Accumulated hypothetical fills at a side/price are subtracted from future displayed capacity even after a version change; unchanged depth never replenishes simulated liquidity. This intentionally underestimates repeated capacity. Network latency, competition, hidden liquidity, and endogenous market impact remain unmodeled.

No passive order fills are fabricated. No live endpoint exists to enable by changing a flag. A separate implementation and explicit live authorization would be required.

## Research usage

`risk.allocate` takes an explicit joint-world payoff matrix, weights, existing terminal wealth, conservative marginal costs and capacity. It optimizes expected log wealth or expected wealth subject to cash and scenario wealth floors. Output is continuous: round down and revalidate the entire portfolio before use. The Gaussian factor generator is for correlation sensitivity, not fitted election probabilities. Derive chamber outcomes from complete seat-level worlds when those are available.

`prize_expectation` evaluates scenario-aligned opponent terminal values and official tie splitting. It does not infer opponent holdings or optimize rank from today's leaderboard. Do not increase risk merely because a guessed opponent model rewards it.

Replay uses receipt ordering and the same strategy/paper engine. It respects first-observed forecasts and account checkpoints. It stops trading when account state is stale or changes, instead of pretending an initial portfolio remains authoritative indefinitely. Use a new database for each latency/depth/haircut setting. Reserve temporal holdouts before tuning; use purged folds and block/cluster-aware uncertainty. Multiple quotes from one election are not independent outcome labels.
