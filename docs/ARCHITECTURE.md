# System Architecture

## Purpose

This document explains the current high-level architecture of the trading research and paper-execution system.

It focuses on:

* system boundaries
* module ownership
* data flow
* runtime responsibilities
* research responsibilities
* artifact ownership
* protected interfaces
* machine roles

This document describes the current architecture.

It does not claim that the strategy is profitable or ready for meaningful live capital.

## Architectural goals

The architecture is designed to support:

* reproducible historical research
* realistic backtesting
* explicit treatment of missing data
* separation between research and runtime behavior
* safe paper execution
* clear ownership of state
* auditable decisions and trades
* gradual movement toward real-exchange readiness
* rejection of weak strategies before capital is placed at risk

The preferred design is the smallest robust architecture that:

* fixes problems at the correct ownership layer
* reuses existing contracts
* avoids duplicate logic
* preserves production behavior
* can be verified practically
* supports the project’s real lifecycle

## High-level system map

The system has five main areas:

1. Historical data and research
2. Backtest execution
3. Strategy and scoring
4. Paper runtime
5. Observability and operational support

A simplified flow is:

```
Historical Coinbase data
    |
    v
Historical audit and gap manifest
    |
    v
Physical segment construction
    |
    v
Replay plan
    |
    v
Segment execution
    |
    v
PaperBroker execution model
    |
    v
Decisions, trades, reports, and research events
```

The live paper flow is:

```
Coinbase market data
    |
    v
Raw bar storage
    |
    v
Feature calculation
    |
    v
Market-state and strategy evaluation
    |
    v
PaperBroker
    |
    v
Decisions and trades
    |
    v
Dashboard and operational monitoring
```

## Machine architecture

## LOCAL

Repository:

```
/home/gto5080/Projects/trade
```

LOCAL is the source-development machine.

It owns:

* source editing
* Git history
* documentation changes
* architecture work
* research design
* deployment preparation

LOCAL must not be used for:

* historical backtests
* data-dependent research validation
* scorer campaigns
* production-like runtime checks
* paper-runtime execution

Git truth exists on LOCAL and GitHub.

## OLD-BOX

Repository and runtime directory:

```
/home/kk7wus/Projects/trade
```

OLD-BOX is the execution and data machine.

It owns:

* historical data storage
* backtest execution
* scorer research
* paper runtime
* dashboard runtime
* Jupyter runtime
* data-dependent validation
* operational health checks

OLD-BOX is not the source-control authority.

Source changes should be made on LOCAL and deployed to OLD-BOX.

## Deployment flow

The canonical deployment command from LOCAL is:

```
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh
```

Deployment uses rsync.

Deployment excludes runtime-owned or machine-specific content such as:

* .git
* .env
* data
* Python caches
* local virtual environments
* runtime logs

The deployment process should preserve OLD-BOX configuration and data.

## Docker services

The main Docker services are:

### paper

Runs the paper-trading loop.

Responsibilities include:

* polling market data
* processing closed bars
* evaluating strategy behavior
* updating PaperBroker state
* writing decisions
* writing trades
* enforcing runtime controls

### trade

Provides research and tooling support.

Responsibilities include:

* backtest execution
* scripts
* Jupyter
* research utilities
* command-line validation

### dashboard

Runs the Streamlit dashboard.

Responsibilities include:

* presenting runtime status
* presenting decisions and trades
* supporting operator visibility
* summarizing system health

### Event-Risk service

Runs separately through its own compose file.

It is intentionally isolated from the paper-trading loop.

It produces processed research artifacts but does not currently affect trading behavior.

## Historical research architecture

## Authoritative historical dataset

The main historical research dataset is:

```
coinbase_history_2022_20260209
```

Contract:

* exchange: Coinbase
* symbol: BTC/USD
* storage symbol: BTC_USD
* timeframe: 5 minutes
* start: 2022-01-01T00:00:00Z
* end-exclusive: 2026-02-09T00:00:00Z
* stored bars: 431,842
* confirmed gaps: 7
* physical segments: 8

Raw storage layout:

```
data/raw/{data_tag}/{SYMBOL_STORAGE}/{timeframe}/date=YYYY-MM-DD/bars.parquet
```

No synthetic bars are inserted.

No data from another exchange is substituted.

## Gap manifest

Authoritative gap manifest:

```
files/research/contracts/coinbase_history_2022_20260209_gaps.json
```

The gap manifest records confirmed missing intervals.

Gap intervals use:

```
[start, end_exclusive)
```

The manifest is part of the historical research contract.

A historical run must not silently ignore a confirmed gap.

## Historical dataset ownership

Primary module:

```
files/research/historical_dataset.py
```

This module owns:

* manifest parsing
* full-dataset audit
* partition validation
* timestamp validation
* cadence validation
* duplicate detection
* physical segment construction
* range normalization
* gap-boundary validation
* warmup-safe slicing
* requested-range resolution

It is the authoritative historical-data layer.

Other modules should not recreate its gap or segmentation rules.

## Historical dataset audit

The historical audit verifies facts such as:

* first available timestamp
* last available timestamp
* stored bar count
* expected bounds
* duplicate absence
* cadence validity
* gap agreement
* physical segment continuity

The audit includes the loaded bars required for downstream historical slicing.

Because the audit performs real loading and validation, public interfaces that return it should use names that clearly signal their cost.

## Physical segments

Each continuous section of historical data is represented as a physical segment.

A physical segment:

* contains only continuous bars
* never crosses a confirmed gap
* has its own feature history
* has its own warmup
* has its own tradable start
* may be too short to produce decisions

The historical dataset contains eight physical segments.

The three-bar segment between the final two confirmed outages remains visible and produces zero eligible decision bars.

It is not deleted or merged.

## Requested historical dataset

A requested research range may intersect one or more physical segments.

The historical data layer resolves that range into segment slices.

Bars before the requested start may be included as warmup only when they belong to the same physical segment.

No pre-gap bar may warm a post-gap segment.

A requested range crossing a complete gap is valid.

A requested boundary inside a gap is invalid.

## Replay architecture

Primary module:

```
files/backtest/replay.py
```

This module owns:

* ReplaySegment
* ReplayPlan
* conversion of resolved historical datasets into replay plans
* conversion of legacy DataFrames into replay plans

It does not own:

* manifest discovery
* historical data loading
* full audit
* strategy behavior
* broker execution

Its role is translation from resolved data contracts into replay contracts.

## Replay segment

A replay segment contains the information required to execute one continuous portion of data.

Typical facts include:

* segment identity
* physical segment identity
* replay bars
* requested-range bounds
* tradable start
* warmup relationship
* segment end

The replay segment does not decide why the segment ends.

That classification belongs to the run-level engine.

## Replay plan

A replay plan contains:

* ordered replay segments
* run-level data identity
* requested bounds
* replay metadata
* source-contract information

The engine executes the segments in order.

## Backtest engine architecture

Primary module:

```
files/backtest/engine.py
```

The engine owns run-level orchestration.

Responsibilities include:

* resolving the source type
* building the replay plan
* classifying segment boundaries
* creating boundary policies
* executing segments in order
* aggregating counts
* aggregating artifact paths
* asserting state isolation
* sequencing research execution events
* returning BacktestResult

The engine should not duplicate historical audit or segmentation logic.

## Backtest source selection

The engine supports:

* legacy replay paths
* manifest-backed historical replay paths

New historical research should use the manifest-backed path.

Legacy behavior remains supported for reproducibility and regression testing.

The system should not choose a source type through a silent file-existence fallback.

Source contracts should be explicit.

## Segment execution architecture

Primary module:

```
files/backtest/segment_executor.py
```

This module executes exactly one replay segment.

Responsibilities include:

* feature calculation
* feature validation
* market-state evaluation
* strategy entry evaluation
* strategy exit evaluation
* PaperBroker interaction
* decision writing
* trade writing
* final-bar entry cancellation
* gap-boundary forced exit
* returning segment results
* returning typed boundary-action facts

It does not own:

* manifest loading
* physical segmentation
* boundary classification
* research event IDs
* run-level event sequencing

## Boundary policy

The engine provides an explicit boundary policy to the segment executor.

Possible boundary types include:

* gap boundary
* requested range end
* dataset end

The executor follows the policy but does not infer it from manifest details.

This preserves clear ownership:

* historical layer defines the data contract
* engine classifies the boundary
* executor performs the allowed action

## Boundary entry behavior

When an entry signal appears on the final available bar but no legal next bar exists:

* the strategy intent remains visible
* the pending entry is cancelled
* no future position is created
* a blocked reason is recorded
* a typed action fact may be returned

Current blocked reasons include:

```
entry_cancelled_gap_boundary
entry_cancelled_requested_range_end
entry_cancelled_dataset_end
```

## Exit ordering

Normal exit logic takes priority over forced gap exit.

Final-bar evaluation order is:

1. Trailing-stop update and normal exit evaluation
2. Market non-tradable exit
3. Stop-hit exit
4. Time-stop exit
5. Gap-boundary forced exit if still open

This prevents duplicate exits and preserves normal strategy behavior.

## Gap forced exit

When a position remains open at a physical gap boundary:

* it closes at the final valid pre-gap timestamp
* it uses the final valid pre-gap close as the reference price
* existing fees and slippage are applied once
* exit reason is:

  segment_end_forced_exit

The broker must be flat before the next physical segment begins.

Requested-range end and dataset end do not automatically force-close positions.

They may return unresolved final-position metadata.

## PaperBroker architecture

Primary module:

```
files/broker/paper.py
```

PaperBroker owns:

* paper positions
* pending entries
* entry execution
* exit execution
* fee application
* slippage application
* trailing-stop state
* cooldown
* cumulative realized PnL
* closed-trade count
* daily accounting
* segment-safe reset behavior

## Broker state categories

Broker state is divided conceptually into:

### Segment-local state

Must not cross a confirmed gap:

* active position
* pending entry
* trailing stop
* trailing anchor
* cooldown

### Run-level accounting

May remain across physical segments:

* cumulative realized PnL
* number of closed trades

The broker reset operation requires the broker to be flat.

## Boundary-safe broker methods

Current boundary-safe methods include:

```
cancel_pending_entry(symbol, now_ts_ms)
```

and:

```
reset_segment_state(symbol)
```

These methods are called explicitly by the research execution path.

They do not alter live behavior unless invoked.

## Strategy architecture

Primary modules:

```
files/strategy/rules.py
files/strategy/filters.py
```

Responsibilities include:

* entry conditions
* exit conditions
* trend interpretation
* volatility interpretation
* market tradability
* ATR trailing-stop rules
* time-stop behavior

Strategy modules should not own:

* historical data loading
* replay segmentation
* artifact paths
* run orchestration
* campaign selection

## Scorer architecture

Important modules include:

```
files/models/entry_model.py
files/research/scorer_walk_forward.py
files/research/scorer_trial.py
files/research/scorer_search_config.py
files/research/scorer_parameter_space.py
files/research/scorer_metrics.py
```

The scorer converts feature and market information into entry confidence or candidate behavior.

Research modules own:

* parameter definitions
* frozen configuration
* trial identity
* fold planning
* candidate metrics
* candidate comparison

They must not bypass the authoritative historical data contract.

## Walk-forward planning

The intended public design for new walk-forward research is:

* load one audited historical research source
* define folds using half-open intervals
* validate fold boundaries through the historical data layer
* resolve each fold using existing segmentation machinery
* calculate deterministic fold statistics
* preserve frozen legacy campaigns separately

Fold ranges should use:

```
[start_ts_ms, end_ts_ms_exclusive)
```

This avoids artificial final-bar timestamps such as:

```
23:59:59.999
```

and avoids timeframe-specific configuration such as:

```
23:55:00
```

## Planned historical research source contract

The intended contract is conceptually:

```
HistoricalResearchSource
```

It should contain or expose:

* HistoricalDatasetAudit
* physical segment descriptors
* manifest fingerprint
* data tag
* symbol
* timeframe
* timeframe step
* dataset start
* dataset end-exclusive
* first available timestamp
* last available timestamp
* stored bar count
* gap count
* physical segment count
* manifest path

The resolver should use a cost-signaling name such as:

```
load_and_resolve_historical_research_source
```

This operation performs real loading and a full audit.

## Fold statistics

Planned deterministic fold statistics include:

```
stored_bars_in_requested_window
replay_bars_including_warmup
warmup_bars_total
structurally_eligible_bar_count
physical_segment_count
gap_count_crossed
```

The following relationship should hold when the fields use these exact meanings:

```
replay_bars_including_warmup
=
warmup_bars_total
+
structurally_eligible_bar_count

```
Structurally eligible bar count means bars at or after each segment’s tradable start.

It does not predict how many decision rows the executor will ultimately write.

## Data feature architecture

Primary module:

```
files/data/features.py
```

Responsibilities include:

* calculating indicators
* preparing feature columns
* validating latest features
* supporting strategy and scorer inputs

Feature calculations must not cross physical historical gaps.

Historical execution calculates features independently for each segment.

## Market data architecture

Primary module:

```
files/data/market.py
```

Responsibilities include:

* fetching market bars through CCXT
* normalizing exchange data
* supporting closed-bar runtime behavior

The runtime should process only the latest closed bar.

Incomplete current bars must not be treated as closed decisions.

## Storage architecture

Primary module:

```
files/data/storage.py
```

Responsibilities include:

* parquet storage
* loading recent bars
* append behavior
* atomic writes
* replayed-bar warnings
* path-based dataset access

Canonical raw layout:

```
data/raw/{exchange}/{SYMBOL_STORAGE}/{timeframe}/date=YYYY-MM-DD/bars.parquet
```

## Path architecture

Primary module:

```
files/data/paths.py
```

Responsibilities include:

* safe exchange names
* safe symbols
* safe timeframe names
* canonical artifact paths
* processed-data path construction

Path naming should remain centralized.

Consumers should not independently reconstruct canonical paths.

## Decisions architecture

Primary module:

```
files/data/decisions.py
```

Decisions record system behavior for each processed closed bar.

Decision artifacts include information such as:

* timestamp
* market state
* trend
* volatility
* entry intent
* blocked reason
* position state
* stop and trail state
* cooldown
* exit intent
* unrealized PnL

The system aims for one decision per processed closed bar.

Decision writing includes restart-safe deduplication.

## Trades architecture

Primary module:

```
files/data/trades.py
```

Trades record completed paper or backtest positions.

Trade artifacts include:

* entry timestamp
* exit timestamp
* side
* quantity
* entry price
* exit price
* exit reason
* fees
* slippage
* realized PnL
* cumulative realized PnL
* closed-trade count
* stop price
* market reason

The trade schema is shared between relevant execution paths.

## Research execution events

Primary module:

```
files/research/execution_events.py
```

Canonical path:

```
data/processed/reports/{backtest_exchange}/{SYMBOL_STORAGE}/{timeframe}/research_execution_events.csv
```

The artifact exists only for manifest-backed gap-aware research runs.

Legacy runs do not create it.

Current schema:

```
event_id
event_sequence
run_id
event_ts_ms
event_type
segment_id
gap_id
boundary_type
position_side
reference_price
related_exit_reason
```

Current event types include:

```
segment_boundary_reached
entry_cancelled
position_forced_exit
```

The engine owns event sequencing.

The serializer owns strict schema validation.

## Event-Risk architecture

Primary Event-Risk output paths:

```
data/processed/event_risk/current.json
data/processed/event_risk/history.csv
```

Event-Risk is treated as a first-class processed artifact.

Its design goals include:

* explicit schema
* small stable enums
* clear freshness semantics
* machine-readable reason codes
* fail-safe status handling
* clear ownership

Event-Risk remains disconnected from paper trading.

It may later be tested as an independent filter or feature after the technical scorer and exit logic are validated.

## Paper runtime architecture

Primary live loop:

```
files/main.py
```

The runtime follows a closed-bar contract.

A simplified runtime sequence is:

1. Fetch market data.
2. Store raw bars.
3. Load recent data.
4. Calculate features.
5. Validate features.
6. Determine market state.
7. Evaluate entry and exit behavior.
8. Update PaperBroker.
9. Write one decision.
10. Write trades when positions close.
11. Sleep until the next loop.

## Closed-bar contract

The runtime processes the last closed bar only.

The decision timestamp represents the bar-close timestamp.

The system should not process the same closed bar twice.

Restart-safe deduplication is seeded from the existing decision artifact.

## Runtime controls

Important runtime controls include:

* STOP
* HALT
* ARM
* daily loss limit
* position limit
* order-size limit
* degraded mode
* feature validation
* cadence monitoring

Runtime flag directory on OLD-BOX:

```
/home/kk7wus/trade_flags
```

Important files include:

```
STOP
HALT
ARM
```

## Dashboard architecture

The Streamlit dashboard provides operator visibility.

It should summarize underlying artifacts rather than invent a second source of truth.

Dashboard responsibilities may include:

* service status
* runtime health
* latest decisions
* latest trades
* position state
* risk state
* Event-Risk summary
* research result summaries

When dashboard output differs from an underlying artifact, the artifact remains authoritative until the discrepancy is resolved.

## Artifact hierarchy

Important artifact groups include:

### Raw data

```
data/raw
```

### Decisions

```
data/processed/decisions
```

### Trades

```
data/processed/trades
```

### Reports

```
data/processed/reports
```

### Event-Risk

```
data/processed/event_risk
```

### Research baselines

```
data/processed/research_baselines
```

Artifacts should be isolated by:

* data tag or backtest exchange
* symbol
* timeframe
* run identity

## Regression architecture

The project uses deterministic regression evidence to preserve behavior.

Important regression areas include:

* legacy backtest behavior
* normalized decision output
* normalized trade output
* gap-boundary handling
* live-versus-backtest equivalence
* artifact schema stability

Raw artifact hashes may differ when output namespaces differ.

Behavioral comparison should normalize fields that are expected to differ only by run identity or output namespace.

## State ownership summary

## HistoricalDatasetAudit

Owned by:

```
files/research/historical_dataset.py
```

Represents:

* loaded historical bars
* validated dataset facts
* gap agreement
* source bounds

## Physical segments

Owned by:

```
files/research/historical_dataset.py
```

Represent:

* continuous historical intervals
* no-gap boundaries
* segment identity

## ReplayPlan

Owned by:

```
files/backtest/replay.py
```

Represents:

* executable ordered replay segments

## Boundary classification

Owned by:

```
files/backtest/engine.py
```

Represents:

* why a segment ends
* what boundary policy applies

## Segment execution

Owned by:

```
files/backtest/segment_executor.py
```

Represents:

* execution of one continuous segment

## Trading state

Owned by:

```
files/broker/paper.py
```

Represents:

* positions
* pending entries
* trailing state
* cooldown
* accounting

## Strategy behavior

Owned by:

```
files/strategy/rules.py
files/strategy/filters.py
```

Represents:

* market interpretation
* entry and exit logic

## Research event serialization

Owned by:

```
files/research/execution_events.py
```

Represents:

* strict research-event artifact writing

## Run orchestration

Owned by:

```
files/backtest/engine.py
```

Represents:

* source selection
* segment ordering
* result aggregation
* run-level events

## Protected boundaries

The following boundaries should remain explicit:

* research versus paper runtime
* historical audit versus replay translation
* replay planning versus segment execution
* segment execution versus run orchestration
* strategy behavior versus campaign planning
* artifact serialization versus business logic
* Event-Risk versus trade execution
* LOCAL editing versus OLD-BOX execution
* new manifest-backed research versus frozen legacy research

## Architecture review rules

A proposed architectural change should answer:

* What problem is being fixed?
* What evidence supports it?
* What is the root cause?
* Which module should own the fix?
* Which interfaces are affected?
* What behavior must remain unchanged?
* How will the result be verified?
* Is the new interface needed by a real caller?
* Does the change duplicate existing logic?
* Does the change increase operational risk?

## Current architectural limitations

The main known limitations include:

* walk-forward planning still needs full public historical-source integration
* there is not yet a multi-trial campaign runner that reuses one audited source
* real-exchange execution is not implemented safely enough for meaningful capital
* exchange reconciliation is incomplete
* partial-fill and cancel-failure handling are not yet proven
* research result summaries can become more informative
* formal automated test coverage remains incomplete
* profitability remains unproven

## Future architecture direction

Expected future work includes:

1. Public audited historical research-source contract
2. Manifest-backed half-open fold planning
3. Deterministic scorer campaign runner
4. One audited source per campaign process
5. Versioned campaign manifests
6. Candidate stability reporting
7. Cost-stress reporting
8. Locked final out-of-sample evaluation
9. Extended forward paper testing
10. Real-exchange order adapter
11. Exchange balance and position reconciliation
12. Partial-fill and retry handling
13. Live safety and alerting
14. Tiny-capital operational validation

Future work should be added only when the preceding owner and caller are clear.

## Architectural principle

The project should not become more complicated merely because additional abstractions are possible.

The system should become more explicit, testable, reproducible, and informative.

The best architecture is the smallest robust design that helps determine whether the strategy has a real edge and prevents unsafe advancement when it does not.
