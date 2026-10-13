# Verified exchange mechanics

Verified 2026-10-13 against [the official API reference](https://sig.thesuper.market/api/v1/docs), authenticated successful GET responses, and [competition rules](https://predictionscup.com/rules/). `docs/api/read-schemas.json` extracts the relevant successful-response schemas. `scripts/audit_api.py` checks local captures without publishing private data.

## Tournament and settlement

The Midterm Elections tournament starts with 100,000 SUSQies and closes November 4, 2026 at noon Eastern (17:00 UTC). Positions lock at the deadline. Final ranking is based on balances after all markets resolve, not simply the displayed mark at the deadline. The first three prizes are 30,000 / 5,000 / 2,500 USD, with pooled prizes split across occupied tied ranks. API bots are permitted under the same single-account rules. Resolution criteria can be amended; the implementation rechecks the contract tree before paper decisions.

`GET /tournaments/{slug}` returns the UUID used in `tournamentId`; this project uses the explicit `midterm-elections` scope. An organization-bound key's omitted scope resolves to its organization's default tournament. Do not rely on that default. Explicit scoped portfolio routes use the slug; exchange data and orders use the UUID.

Market listings contain exchange IDs, status, and settlement dates. Exact resolution metadata is in `/markets/{id}/nodes`, not necessarily `/markets/{id}`. Maine and NY-17 are party-winner election contracts with race and stage IDs. Senate control is freeform: it includes caucusing independents, a Vice-Presidential tie-break, and a President Pro Tempore fallback. A generic third-party Senate forecast is not automatically an exact settlement match.

## Books, fills, and cash

- `/exchanges/{id}/orderbook`: YES-normalized bids/asks. Buying NO uses `1 - YES bid`; selling NO uses `1 - YES ask`. `asOf` supplies engine sequence and capture time; unversioned or stale observations cannot execute paper orders.
- `/portfolio/fills` and tournament fills: quantity is outcome-signed, **not buy/sell-signed**. Price is for the actual outcome; a NO fill reports a NO price. Join `orderId` to orders for the action. Do not reuse realtime parsing here: realtime fill prices are YES-denominated.
- Positions: positive quantity means YES, negative means NO. `avgCost` is outcome cost; `currentPrice` is YES valuation. Reconcile exact lots/cost bases rather than screenshot-rounded average prices.
- Open order `quantity` is the remaining executable size. It is not original order size less `quantityFilled`; that field is null while open.
- Resting buys do not reserve exchange cash. The system conservatively reserves their full worst-case cost. Paper seeding requires zero real open orders to avoid assuming fills against the account's own displayed liquidity or ignoring resting sell exposure.
- Account `balance` can carry more precision than the tournament's rounded `myBalance`; reconciliation uses the former. ALL collateral can increase buying power, but this system does not borrow against it.
- New limits use a 0.005 tick, between 0.005 and 0.995. Market-order encodings 0/1 are intentionally unavailable in paper intents.

## History, consistency, and limits

Reads: 100/minute/account; writes: 30/minute/account. The client uses at most approximately 75 reads/minute before network time. This is a per-process budget, not distributed coordination. Run one collector. Market data may be cached for 1–2 seconds. A full-universe sweep takes minutes; re-fetch all basket legs immediately before assessing a trade.

Cursor history has `pagination.hasMore`/`nextCursor`; tournament discovery uses offset pagination. `coverage.complete` does not mean the caller has consumed all pages. Both are checked. Raw pages retain projection sequences, but independently read account endpoints do not form an atomic snapshot. The collector brackets cash/inventory and compares full fills, orders, and FIFO lots. A mismatch blocks paper seeding. Capture is durable even if later normalization fails.

The REST tape's `side` is YES/NO outcome, not aggressor direction. Candle history omits no-trade buckets and is not historical executable depth. This implementation backfills trades; it does not invent historical books or manufacture fills from OHLCV.

Realtime is best-effort and requires REST recovery on reconnects, revision gaps, and `resyncRequired`. This implementation deliberately uses REST for a small watchlist; it does not pretend to offer realtime queue reconstruction. The universe scan is for discovery only.

## Basket execution distinction

`POST /orders/batch` is best-effort and is not atomic. `/orders/multi-leg` defaults to atomic placement, but accepted legs may rest or partially fill. The documented `executionMode: "allOrNone"` instead requires all quantities to fill within their limits or executes nothing on supported engine scopes. The optional relationship constraint is preflight validation, not a lock protecting a payoff bound during execution.

No POST/DELETE request was made. The documentation describes all-or-none behavior, but participant-specific execution/rejections have not been live-tested. A positive paper basket bound is contingent on resolution assumptions, costs, complete execution and account inventory compatibility. It is not proof of a realizable risk-free profit.
