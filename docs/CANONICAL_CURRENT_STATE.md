# CANONICAL CURRENT STATE — MJÖLNIR

Date: 2026-07-30

This document is the authoritative current system state.

If an older handoff, archived snapshot, notebook note, or generated
summary conflicts with this document, this document wins.

## 1. Mission

Build a reliable, reproducible, observable paper-trading and research
system that can discover robust strategy and scorer parameter
combinations with positive out-of-sample performance and controlled
risk.

The system has two separate operational layers:

1. Runtime and paper-execution layer
2. Historical research and optimization layer

The system is not ready for real-money execution.

The runtime layer is mature enough to support disciplined research.
The main unresolved problem is proving a repeatable trading edge.

## 2. Machine roles

### LOCAL

Repository:

`/home/gto5080/Projects/trade`

Responsibilities:

- edit source code
- manage Git
- maintain documentation
- design research workflows
- deploy code to OLD-BOX

LOCAL is not used for:

- backtests
- historical data execution
- data-dependent validation
- scorer optimization runs

### OLD-BOX

Repository/runtime directory:

`/home/kk7wus/Projects/trade`

Responsibilities:

- live paper loop
- historical market data
- backtests and scorer research
- dashboard
- Jupyter tooling
- operator controls
- runtime-owned `.env`
- runtime-owned `data/`
- runtime-owned `trade_flags/`

OLD-BOX is operational only. Git is not used there as the deployment
or source-control mechanism.

## 3. Deployment contract

Canonical LOCAL deployment command:

`OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh`

Deployment behavior:

- uses rsync
- does not delete target-only files
- excludes runtime-owned state
- deploys source from LOCAL to OLD-BOX

Runtime-owned paths excluded from deployment include:

- top-level `/data/`
- `.env`
- `trade_flags/`
- logs and cache files

The rsync exclusion must use `/data/`, not `data/`.

The leading slash is required so source modules under `files/data/`
remain deployable.

## 4. Git state and source tracking

Git truth exists on LOCAL and GitHub.

Core source modules now correctly tracked include:

- `files/data/decisions.py`
- `files/data/paths.py`
- `files/data/trades.py`
- `files/data/historical_backfill.py`

A previous `.gitignore` rule used:

`data/`

That incorrectly ignored all directories named `data`, including
`files/data/`.

The corrected rule is:

`/data/`

This ignores only the repository's top-level runtime-data directory.

## 5. Docker services

Primary `docker-compose.yml` services:

- `trade`
- `paper`
- `dashboard`

### trade

Purpose:

- Jupyter
- backtests
- research tools
- historical data operations
- one-off health and validation commands

Mounted paths include:

- `./notebooks:/work/notebooks`
- `./files:/work/files`
- `./ops:/work/ops`
- `./data:/work/data`
- `/home/kk7wus/trade_flags:/home/kk7wus/trade_flags`

The `ops` mount was added so research CLIs are directly available
inside the tooling container.

### paper

Purpose:

- closed-bar live paper loop

Command:

`python -m files.main`

Mounted paths include:

- `./files:/work/files`
- `./data:/work/data`
- `/home/kk7wus/trade_flags:/home/kk7wus/trade_flags`

The paper service does not require the `ops` mount.

### dashboard

Purpose:

- Streamlit operator and research visibility

Port:

`127.0.0.1:8501`

## 6. Active paper runtime

Current paper namespace:

`paper_oldbox_live`

Current verified runtime values:

- `DATA_TAG=paper_oldbox_live`
- `CCXT_EXCHANGE=coinbase`
- `SYMBOL=BTC/USD`
- `TIMEFRAME=5m`
- `DRY_RUN=1`
- `ARMED=1`

Current behavior:

- market data fetched every loop
- raw bars persisted
- one decision written per closed 5-minute bar
- repeated loop ticks safely skip already-processed bars
- runtime remains restart-safe and timestamp-deduplicated

## 7. Paper health state

The correct health command must explicitly use the paper namespace.

Canonical OLD-BOX command:

`DATA_TAG=paper_oldbox_live CCXT_EXCHANGE=coinbase SYMBOL=BTC_USD TIMEFRAME=5m make health`

Latest verified health result:

- healthcheck pass
- zero bad recent rows
- zero bad tail rows
- 249 clean trailing cadence differences
- raw bars fresh
- decisions fresh
- exact live namespace resolved correctly

A health check using `coinbase` as the processed namespace is invalid
for the active paper runtime and will report missing decisions.

## 8. Operator control plane

Runtime flag directory:

`/home/kk7wus/trade_flags`

Important controls:

- `STOP`
- `HALT`
- `ARM`
- `status.txt`

Semantics:

- `STOP` is the strongest stop condition
- `HALT` blocks new entries
- `ARM` permits entries when other safety conditions allow
- `status.txt` exposes runtime/operator status

Flag-file changes take effect on the next loop iteration and do not
require a container restart.

## 9. Restart rules

### Bind-mounted code changed

Deploy from LOCAL, then restart only the affected service if runtime
determinism requires it.

Typical paper restart:

`docker compose restart paper`

### Compose or container-mount change

Recreate only the affected service.

Example for tooling-only changes:

`docker compose up -d --no-deps --force-recreate trade`

### Environment change

Recreate the affected service so Compose resolves the new environment.

### Flag-file change

No restart required.

## 10. Runtime data contracts

Canonical raw-bar layout:

`data/raw/{data_tag}/{SYMBOL_STORAGE}/{timeframe}/date=YYYY-MM-DD/bars.parquet`

Canonical decisions layout:

`data/processed/decisions/{data_tag}/{SYMBOL_STORAGE}/{timeframe}/decisions.csv`

Canonical trades layout:

`data/processed/trades/{data_tag}/{SYMBOL_STORAGE}/{timeframe}/trades.csv`

Canonical manifest-backed research execution-event layout:

`data/processed/reports/{backtest_exchange}/{SYMBOL_STORAGE}/{timeframe}/research_execution_events.csv`

The research execution-event artifact is created only for
manifest-backed gap-aware runs. Legacy backtests do not create it.

Primary observability truth:

- decisions CSV
- trades CSV
- raw Parquet bars
- mission-specific proof artifacts

Decision semantics preserve the distinction between:

- strategy or signal reason
- execution or guardrail blocked reason

### Gap-aware historical replay

The manifest-backed historical loader and backtest orchestration are
implemented for:

- data tag: `coinbase_history_2022_20260209`
- symbol: `BTC/USD`
- timeframe: `5m`
- dataset range:
  `[2022-01-01T00:00:00Z, 2026-02-09T00:00:00Z)`
- stored bars: 431,842
- confirmed gaps: 7
- physical replay segments: 8

Canonical gap manifest:

`files/research/contracts/coinbase_history_2022_20260209_gaps.json`

Implemented replay rules:

- the complete dataset is audited before range slicing
- gaps and segments use inclusive-start, exclusive-end intervals
- features are computed independently inside each physical segment
- feature warmup never borrows bars across a confirmed gap
- a segment with insufficient bars remains present but produces no
  decisions
- pending final-bar entries are cancelled when no next bar is legally
  available
- normal exit logic runs before any gap-boundary forced exit
- positions still open at a physical gap boundary are closed at the
  final valid pre-gap close
- position, trailing, pending-entry, and cooldown state cannot cross a
  gap
- cumulative realized PnL and closed-trade totals are preserved across
  segments
- requested-range and dataset ends may expose unresolved final position
  state
- legacy backtests preserve their previous behavior

Verified complete-run result:

- bars total: 431,842
- decision rows: 430,446
- trade rows: 266
- decision timestamps inside gaps: 0
- trade entry or exit timestamps inside gaps: 0
- duplicate decision timestamps: 0
- full gap-aware contract audit: PASS

Research execution events use a separate strict artifact with these
event types:

- `segment_boundary_reached`
- `entry_cancelled`
- `position_forced_exit`

## 11. Execution and safety state

Confirmed runtime protections include:

- closed-bar processing
- one decision per closed bar
- restart-safe decision deduplication
- next-bar entry modeling
- explicit STOP, HALT, and ARM controls
- degraded-mode behavior
- feature validation
- cadence monitoring
- daily and position-risk controls
- machine-readable blocked reasons
- trailing-stop state
- cooldown tracking

The current safety problem is not basic order discipline.

The larger unresolved problem is strategy profitability.

## 12. Current strategy policy

Current live policy:

- LONG enabled
- SHORT quarantined

SHORT setups remain observable but are explicitly blocked.

Expected blocked reason:

`trend_down_but_short_disabled`

The quarantine preserves:

- SHORT signal visibility
- strategy observability
- comparison capability
- ability to reconsider only after sufficient evidence

SHORT must not be re-enabled without robust evidence.

## 13. Entry-sequence research branch

The entry-sequence candidate was:

- `bar_range_atr <= 1.20`
- four-bar rejected-setup suppression

Observed development evidence:

- 3 independent pass episodes
- 3 executed trades
- 3 wins
- 0 losses
- net result: positive $22.686719
- active and profitable in all three development periods

Final decision:

- rejected for insufficient trade count
- only 3 observed trades
- minimum evidence requirement was 8 trades
- validation and out-of-sample periods remain locked
- no production changes were made

The candidate is frozen and must not be retrospectively retuned using
the expanded historical dataset.

## 14. Scorer research framework

Tracked scorer research modules include:

- `files/research/scorer_search_config.py`
- `files/research/scorer_parameter_space.py`
- `files/research/scorer_trial.py`
- `files/research/scorer_metrics.py`
- `files/research/scorer_walk_forward.py`
- `files/research/run_single_scorer_trial.py`
- `files/research/print_walk_forward_splits.py`

Research goals:

- deterministic parameter generation
- isolated trial outputs
- chronological evaluation
- repeatable walk-forward splits
- risk-aware metrics
- robust out-of-sample profitability
- avoidance of in-sample-only optimization

## 15. Historical Coinbase dataset

Historical namespace:

`coinbase_history_2022_20260209`

Storage root:

`data/raw/coinbase_history_2022_20260209/BTC_USD/5m`

Coverage:

- start inclusive: `2022-01-01T00:00:00Z`
- end exclusive: `2026-02-09T00:00:00Z`

Final audit:

- 1,500 daily Parquet partitions
- 431,842 stored bars
- 432,000 theoretical bars
- 158 confirmed missing bars
- zero duplicate timestamps
- exact first timestamp
- exact last timestamp
- seven cadence gaps
- full audit passed

The historical namespace is isolated from `paper_oldbox_live`.

## 16. Historical backfill implementation

Reusable implementation:

`files/data/historical_backfill.py`

CLI:

`ops/research/backfill_ohlcv.py`

Capabilities:

- deterministic CCXT pagination
- inclusive start and exclusive end
- bounded chunk execution
- validation before persistence
- retry with exponential backoff
- exact range validation
- duplicate detection
- cadence validation
- OHLC relationship validation
- atomic daily Parquet persistence
- safe timestamp-deduplicated reruns
- dry-run by default
- explicit `--write` requirement

Default chunk size:

30 days

Default page size:

300 rows

## 17. Confirmed Coinbase source outages

Authoritative machine-readable manifest:

`files/research/contracts/coinbase_history_2022_20260209_gaps.json`

Confirmed gaps:

1. `2022-08-12T11:25:00Z` to `2022-08-12T11:30:00Z`
   - 1 missing 5-minute bar

2. `2023-03-04T17:00:00Z` to `2023-03-04T21:35:00Z`
   - 55 missing 5-minute bars

3. `2023-05-19T07:45:00Z` to `2023-05-19T08:25:00Z`
   - 8 missing 5-minute bars

4. `2024-05-31T22:20:00Z` to `2024-05-31T23:15:00Z`
   - 11 missing 5-minute bars

5. `2024-10-26T16:10:00Z` to `2024-10-26T17:15:00Z`
   - 13 missing 5-minute bars

6. `2025-10-25T14:55:00Z` to `2025-10-25T15:00:00Z`
   - 1 missing 5-minute bar

7. `2025-10-25T15:15:00Z` to `2025-10-25T21:00:00Z`
   - 69 missing 5-minute bars

Every gap was also checked against Coinbase's 1-minute feed.

All underlying one-minute candles were absent.

No synthetic bars were created.

No cross-exchange prices were substituted.

## 18. Historical research-use rules

Historical research must not treat the dataset as fully continuous.

Required behavior:

- load the gap manifest
- segment the dataset at confirmed gaps
- prevent simulated positions from silently crossing a gap
- reset or re-warm stateful indicators when appropriate
- avoid interpreting a multi-hour gap as one normal 5-minute return
- keep train, validation, and test windows explicit
- include the data tag and manifest in run artifacts
- maintain deterministic seeds and versioned configurations

A future research loader should expose continuous segments directly.

## 19. Event-risk service

The event-risk service remains separate from live trading.

It is intentionally not wired into the paper loop.

Canonical outputs:

- `data/processed/event_risk/current.json`
- `data/processed/event_risk/history.csv`

The Compose orphan warning for `event_risk` is informational because
the service is intentionally isolated.

Event-risk research may later be tested as an independent filter or
feature after the technical strategy and scorer have stronger evidence.

## 20. Documentation model

Current authoritative documents:

- `docs/CANONICAL_CURRENT_STATE.md`
- `HANDOFF.md`

Historical-backfill mission report:

- `docs/research/historical_backfill_mission_2022_2026.md`

Historical gap manifest:

- `files/research/contracts/coinbase_history_2022_20260209_gaps.json`

Archive documents:

- `docs/ARCHIVE_handoffs.md`
- `docs/ARCHIVE_project_snapshots.md`

Current-state documents should contain current truth only.

Superseded detail belongs in archive documents or mission reports.

## 21. Engineering workflow

Current operating contract:

1. Work one mission at a time.
2. Inspect actual files and interfaces before editing.
3. Do not guess function signatures.
4. Make changes on LOCAL.
5. Commit and push proven source changes.
6. Deploy to OLD-BOX using rsync.
7. Run all data-dependent validation on OLD-BOX.
8. Restart or recreate only the affected service.
9. Verify runtime health after relevant deployment changes.
10. Preserve production behavior unless the mission explicitly changes it.

Preferred command workflow:

- one command or notebook cell at a time
- label LOCAL and OLD-BOX clearly
- wait for output before continuing
- use complete file replacements when practical
- avoid temporary architecture expected to be replaced later

## 22. Current priorities

In order:

1. Build the deterministic multi-trial scorer campaign runner.
2. Load and audit one HistoricalResearchSource per campaign process and reuse it explicitly across trials.
3. Record versioned campaign manifests containing code commit, source fingerprint, folds, candidate identities, execution assumptions, and artifact paths.
4. Run bounded scorer campaigns across the frozen manifest-backed chronological folds.
5. Evaluate candidates using out-of-sample profitability, controlled drawdown, trade-count sufficiency, parameter stability, and realistic cost stress.
6. Preserve all rejected candidates and campaign evidence reproducibly.
7. Prioritize repeatable out-of-sample profitability, controlled drawdown, parameter stability, and realistic costs.
8. Preserve the frozen entry-sequence candidate and locked prior out-of-sample evidence.
9. Continue honest LONG_ONLY paper observation.
10. Keep Event-Risk isolated until its independent research phase.
11. Improve focused automated testing, deployment verification, and operational documentation.
12. Do not move toward real-money execution without a proven strategy edge and verified live-execution safety.

## 23. Non-negotiables

* Do not fabricate missing market data.
* Do not mix prices from another exchange into the Coinbase dataset.
* Do not silently backtest across known data gaps.
* Do not re-enable SHORT without evidence.
* Do not alter the live strategy while unrelated research is underway.
* Do not optimize only for in-sample profit.
* Do not use LOCAL for data-dependent execution.
* Do not overwrite OLD-BOX runtime-owned `.env` or data.
* Do not assume successful HTTP responses contain complete historical data.
* Do not treat a passing backtest as proof without chronological out-of-sample evidence.
* Do not silently fall back from manifest-backed research to a legacy or live-data path.
* Do not change locked validation or final test windows after viewing results.

## 24. Current assessment

System engineering:

* operationally stable enough for research
* observable
* restart-safe
* guarded
* reproducible
* still paper-only

Historical research foundation:

* long-range dataset complete
* 1,500 daily partitions audited
* seven confirmed source gaps documented
* backfill reproducible
* gap-aware loading complete
* eight physical replay segments exposed
* independent post-gap warmup complete
* boundary-safe entry and exit behavior complete
* strict research execution-event artifact complete
* full four-year gap-aware contract audit passed
* legacy backtest behavior preserved

Walk-forward research state:

- public HistoricalResearchSource contract complete
- cost-signaling historical source resolver complete
- manifest_backed_v1 enforcement complete
- half-open chronological folds complete
- exact gap-aware fold planning complete
- deterministic fold statistics complete
- frozen legacy campaign separation complete
- private historical engine-loader dependency removed
- multi-trial campaign runner does not yet exist

Strategy state:

* edge not proven
* SHORT remains quarantined
* LONG_ONLY remains the live paper baseline
* manifest-backed scorer research is the next major research path

Single-trial utility boundary:

* `files/research/run_single_scorer_trial.py` remains a low-level research utility.
* It inherits the general runtime `DATA_TAG` configuration.
* When no historical manifest exists for that tag, the backtest engine may intentionally use the legacy replay path.
* This behavior is preserved for compatibility and is not the authoritative campaign contract.
* The future multi-trial campaign runner must require `manifest_backed_v1`.
* It must resolve and audit one `HistoricalResearchSource` before executing trials.
* It must reuse that resolved source across the entire campaign process.
* It must fail explicitly rather than silently falling back to legacy replay.

## 25. Bottom line

The system now has:

* a healthy live paper runtime
* explicit operator controls
* reliable decision and trade logging
* an isolated historical Coinbase dataset
* 1,500 audited daily partitions
* a machine-readable source-gap manifest
* deterministic chunked historical backfill tooling
* gap-aware historical loading and replay
* eight independently warmed physical replay segments
* boundary-safe entry, exit, and broker-state behavior
* strict research execution events
* verified legacy regression behavior
* a walk-forward scorer research foundation
* an invite-first contributor and review framework
* a disciplined LOCAL-to-OLD-BOX workflow

The next major mission is not more historical loading, replay, or walk-forward planning work.

The next major mission is to build the deterministic multi-trial campaign runner, reuse one audited historical source per campaign process, record complete campaign identity, and begin bounded scorer research across the frozen manifest-backed folds.
