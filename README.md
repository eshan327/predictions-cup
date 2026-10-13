# Predictions Cup

Research and paper-trading system for SIG's 2026 Midterm Elections tournament.

**The API, account reconciliation, and paper workflow have been exercised against actual SIG data. No live order submission or cancellation is implemented. No strategy has demonstrated out-of-sample profitability.**

The goal is to discover a defensible edge, measure executable capacity, and control correlated election exposure. A default run collects data and produces zero trade decisions until reviewed, time-stamped forecasts and settlement mappings are supplied. That is an intentional research gate.

## Install and verify

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
```

Python 3.11+. Set `SIG_API_KEY` in your environment using a secret manager or a hidden shell prompt. The program does not load `.env` automatically. Never put a key in a command argument, notebook, commit, issue, or report. The SIG client has a fixed HTTPS origin and only exposes GET operations.

## Operate

```bash
# Reconcile account, archive all market metadata, collect held-contract books.
pcup collect

# One descriptive universe sweep. ~237 books takes several minutes at the rate cap.
# It is NOT a simultaneous cross-market snapshot.
pcup collect --all-books

# Watch a small set continuously; held exchanges are always included.
pcup collect --exchange 843 --exchange 920 --exchange 959 --cycles 0 --interval 60

# Bounded, fully paginated public trade history. NO synthetic historical books.
pcup backfill --exchange 843 --start 2026-10-12T00:00:00Z --end 2026-10-13T00:00:00Z

# Archive public RTWH Senate forecast, including publisher/availability timestamps.
pcup external

pcup report
pcup health                           # exit 2 if unhealthy/stale
python scripts/audit_api.py --db data/private/research.sqlite
python scripts/research_study.py --db data/private/research.sqlite
```

Use one collector per account: the exchange rate budget is shared with your other clients. The client spaces requests by at least 0.8 seconds, honors Retry-After, retries transient GET failures with bounded backoff, and stops on authentication/schema/pagination failures. Continuous mode stops on an error; investigate before restarting. Ctrl-C stops collection. Run on your own persistent host to retain ongoing history; this repository does not imply a deployed service.

The SQLite database retains response hashes, receipt/request times, pagination coverage, versioned normalized books, reconciliation snapshots, and run status. Account profile fields are removed. Financial history remains private. Back up SQLite with its backup API, not by copying an active database without its WAL.

## Paper trading and replay

```bash
# Empty checked-in inputs deliberately do not generate orders.
pcup paper --forecasts config/forecasts.jsonl --mappings config/mappings.json \
  --limits config/paper-limits.json --paper-db data/private/paper.sqlite --cycles 2 --interval 10

pcup replay --forecasts config/forecasts.jsonl --mappings config/mappings.json \
  --limits config/paper-limits.json --paper-db data/private/replay-001.sqlite

touch STOP                            # block new paper orders; cancel pending on next cycle
rm STOP                               # only after checking the cause
```

See [the runbook](docs/OPERATIONS.md) for forecast inputs, restart behavior, and limitations. Paper orders are local events. SIG holdings and orders are never changed. Use a fresh paper database for each replay or parameter comparison; forward paper resumes from its durable seed/events. Real-account changes halt paper trading instead of silently overwriting simulated inventory.

## Research decisions

- Prefer verified cross-contract payoff bounds and external-forecast discrepancies over speculative microstructure signals.
- Use explicit tournament UUIDs everywhere. An exchange ID is the tradable instrument; a market ID is its container.
- Model YES/NO complements correctly and compare forecasts to executable depth, not display prices.
- Preserve the time information became available. A current forecast cannot explain a historical decision.
- Use joint terminal-outcome scenarios, existing inventory, cash reserves, and worst-case loss. Do not sum independent single-bet Kelly sizes.
- Compare expected wealth and expected log wealth; evaluate tournament prizes only with explicit scenario-aligned opponent assumptions. Current leaderboard values are not terminal opponent forecasts.
- Do not simulate passive fills from candle touches or outcome-signed trade tape. The required queue/aggressor evidence is absent.

[Research findings](docs/RESEARCH_FINDINGS.md) document the actual observations and what they do **not** establish. [API mechanics](docs/API_MECHANICS.md) record the verified contract. [Research plan](docs/RESEARCH_PLAN.md) explains the remaining promotion gates.

## Code layout

| Module | Responsibility |
|---|---|
| `api`, `collection`, `models`, `store` | GET-only ingestion, normalization, private history, reconciliation |
| `external`, `forecast` | RTWH capture, source provenance, as-of estimates and assumption bounds |
| `strategy`, `paper`, `replay`, `operations` | Shared forecast taker, guarded IOC model, recovery and health |
| `risk`, `portfolio` | Joint scenarios, constrained allocation, prize utility and inventory risk |
| `evaluation` | Depth-aware consistency checks, temporal splits, bootstrap/markout diagnostics |
| `research` | Legacy synthetic scanner and elementary scoring helpers; not production signals |

The scenario optimizer is a research tool, not silently wired into autonomous sizing. Until scenario probabilities and mappings are validated, the running paper strategy uses cash and aggregate incremental-cost caps, which conservatively bound all-loss election exposure. There is no leverage or automatic risk escalation to chase rank.
