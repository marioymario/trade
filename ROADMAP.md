# Project Roadmap

## Purpose

This roadmap describes the current direction of the trading research and paper-execution system.

It separates:

* completed work
* current work
* near-term research work
* operational work
* live-readiness work
* long-term possibilities

The roadmap is evidence-driven.

Dates alone do not determine readiness.

A stage advances only when its required technical and research conditions are met.

## Project objective

The current objective is to build a reliable system that can determine whether a trading strategy has a repeatable, risk-controlled edge after realistic costs.

The project is not yet a proven profitable trading system.

The project should be able to produce one of two useful conclusions:

* a strategy is robust enough to justify further testing
* a strategy should be rejected before real money is placed at risk

Both outcomes are valuable.

## Current status

The engineering and research foundation is advanced.

The project currently supports:

* live LONG_ONLY paper execution
* explicit SHORT quarantine
* isolated Event-Risk research/service behavior
* historical data collection and storage
* audited manifest-backed historical datasets
* explicit physical-gap handling
* gap-aware replay
* deterministic chronological walk-forward folds
* deterministic scorer campaigns
* reproducible campaign and candidate identity
* frozen Coinbase USD Research Universe V1
* explicit multi-asset eligibility policy
* frozen PRIMARY_COMPARABLE research population
* research-only equal-USD-notional sizing
* decision, trade, and research-event artifacts
* runtime health and operator controls
* dashboard visibility
* Docker-based execution on OLD-BOX

The historical-data preparation phase is complete.

The campaign/research infrastructure required for multi-asset research is
implemented.

Profitability is not proven.

Meaningful live capital remains inappropriate.

The active experiment and exact immediate next action belong in HANDOFF.md,
not in this roadmap.

## Completed milestone: core paper system

The paper system includes:

* closed-bar processing
* one decision per closed bar
* restart-safe decision deduplication
* next-bar entry modeling
* trailing-stop behavior
* cooldown behavior
* fee and slippage modeling
* position and daily-risk controls
* STOP, HALT, and ARM controls
* degraded mode
* feature validation
* cadence monitoring
* decision artifacts
* trade artifacts

## Completed milestone: live-versus-backtest equivalence

The project established a live-versus-backtest comparison workflow.

Verified areas include:

* timestamp-based decision comparison
* windowed trade comparison
* next-bar entry behavior
* stop-through behavior
* synchronization from a flat state
* normalized artifact comparison

This work reduced uncertainty about whether historical and paper execution follow the same core behavior.

## Completed milestone: SHORT quarantine

SHORT logic remains visible in the system but is not active for paper entries.

Current policy:

* LONG enabled
* SHORT signals observable
* SHORT entries blocked

This prevents unproven SHORT behavior from affecting the active paper baseline.

SHORT should remain quarantined until a separate research case supports re-evaluation.

## Completed milestone: Event-Risk service isolation

A separate Event-Risk service exists.

It produces:

```
data/processed/event_risk/current.json
```

and:

```
data/processed/event_risk/history.csv
```

Event-Risk is not connected to the paper trading loop.

This separation protects the current baseline from an unvalidated external feature.

Event-Risk may later be tested as an independent filter or research feature.

## Completed milestone: original BTC historical dataset audit

The original canonical historical control dataset is:

`coinbase_history_2022_20260209`

Contract:

* exchange: Coinbase
* symbol: BTC/USD
* timeframe: 5 minutes
* interval: 2022-01-01T00:00:00Z through 2026-02-09T00:00:00Z end-exclusive
* stored bars: 431,842
* expected bars: 432,000
* confirmed missing bars: 158
* confirmed outages: 7
* physical segments: 8

No synthetic candles were created.

No data from another exchange was inserted.

This dataset remains an important canonical control source.

It is no longer the entire historical research universe.

The project subsequently expanded to the frozen:

`research_universe_coinbase_usd_v1`

That universe contains 29 verified Coinbase USD spot markets with explicit,
market-specific manifests and heterogeneous historical completeness.

## Completed milestone: gap-aware historical replay

Commit:

```
d4c6f7d Add gap-aware historical replay
```

Completed capabilities include:

* authoritative historical gap manifest
* full historical audit
* physical segmentation
* independent feature warmup by segment
* range validation
* gap-boundary validation
* replay-plan construction
* one-segment execution ownership
* final-bar entry cancellation
* gap-boundary forced exits
* broker state isolation
* strict research execution events
* legacy behavior preservation

Full historical execution results:

* total stored bars: 431,842
* processed decision rows: 430,446
* closed trades: 266
* decisions inside gaps: 0
* trades inside gaps: 0
* duplicate decision timestamps: 0
* physical segments verified: 8
* confirmed gaps verified: 7

## Completed milestone: contributor welcome structure

The project now includes or is adding:

* README.md
* CONTRIBUTING.md
* docs/PROJECT_REVIEW_GUIDE.md
* docs/ARCHITECTURE.md
* docs/RESEARCH_PRINCIPLES.md
* docs/CONTRIBUTOR_ONBOARDING.md
* ROADMAP.md

The contribution model is:

* invite-first
* discussion-first
* review before code
* sustained one-to-one collaboration
* no bulk AI-generated pull requests
* no casual strategy changes
* evidence and verification required

## Current mission

The current mission is to move new walk-forward scorer planning fully onto the public manifest-aware historical contract.

The problem is that current walk-forward planning still depends on private historical loader behavior for split metadata.

Trial execution is already gap-aware through the public backtest path.

The defect is concentrated in split planning and source ownership.

## Current mission design

The intended design includes:

* a public audited historical research-source contract
* a cost-signaling source resolver
* half-open fold ranges
* exact gap-boundary validation
* fold planning through existing historical segmentation
* deterministic fold statistics
* explicit source-contract discrimination
* removal of private engine imports
* preservation of frozen legacy campaigns

Planned source contract:

```
HistoricalResearchSource
```

Expected contents:

* HistoricalDatasetAudit
* physical segment descriptors
* manifest fingerprint
* data tag
* symbol
* timeframe
* timeframe step
* dataset bounds
* first and last available timestamps
* stored-bar count
* gap count
* physical-segment count
* manifest path

Planned resolver name:

```
load_and_resolve_historical_research_source
```

## Current mission fold contract

New research folds should use:

```
[start_ts_ms, end_ts_ms_exclusive)
```

This avoids:

* overlapping adjacent folds
* artificial 23:59:59.999 endpoints
* timeframe-specific 23:55:00 configuration
* unclear inclusive-boundary behavior

Planned fold statistics include:

```
stored_bars_in_requested_window
replay_bars_including_warmup
warmup_bars_total
structurally_eligible_bar_count
physical_segment_count
gap_count_crossed
```

## Completed milestone: manifest-backed walk-forward and campaign infrastructure

The following research infrastructure is implemented:

* public audited HistoricalResearchSource
* half-open chronological fold definitions
* explicit gap-boundary validation
* physical-segment-aware fold planning
* deterministic fold statistics
* deterministic scorer trials
* deterministic campaign identity
* deterministic execution identity
* one audited source reused per campaign process
* isolated campaign artifacts
* resume and reuse validation
* failure preservation
* aggregation
* rejection policy
* ranking policy
* Git and source identity recording
* realistic transaction-cost scenarios

Frozen ordinary research folds are:

Fold 1:

* train 2022
* validate 2023-H1

Fold 2:

* train through 2023-H1
* validate 2023-H2

Fold 3:

* train through 2023
* validate 2024

The 2025+ period remains protected out-of-sample data.

## Completed milestone: Coinbase USD Research Universe V1

The project now has a frozen multi-asset historical research universe:

`research_universe_coinbase_usd_v1`

The universe contains 29 verified Coinbase USD spot markets.

Its membership and identity are frozen.

Material changes require a new universe version.

The current PRIMARY_COMPARABLE population is:

* BTC/USD
* ETH/USD
* SOL/USD
* ADA/USD
* XLM/USD
* LINK/USD
* DOGE/USD
* LTC/USD

Historical completeness is not equal across all markets.

Missing data remains explicit rather than fabricated.

## Completed milestone: cross-asset comparable research sizing

The research system supports an optional explicit USD order-notional
contract.

This allows capital-dependent metrics such as raw dollar PnL to be compared
across assets under equivalent economic exposure.

The research sizing override:

* is optional
* is disabled by default
* is isolated from live sizing
* participates in campaign identity when supplied
* preserves legacy campaign identity when absent

## Completed milestone: PRIMARY-8 equal-USD-notional baseline

The first authoritative economically comparable PRIMARY_COMPARABLE baseline
is complete and audited.

Contract:

* eight PRIMARY_COMPARABLE assets
* one frozen strategy/scorer configuration
* scorer contract: entry_scorer_v3_normalized_slope
* frozen trial: trial_096291cf0738ff2f
* 100 USD research order notional
* three frozen chronological validation folds
* realistic costs
* protected 2025+ out-of-sample data untouched

Execution:

* 8/8 campaigns completed
* 48/48 planned backtests completed
* zero failure rows

Result:

* BTC/USD was eligible under the current rejection policy
* BTC had 3/3 positive validation folds
* seven of eight PRIMARY assets were rejected
* several rejected assets remained profitable in aggregate but failed
  worst-fold requirements

This establishes that aggregate profit alone is insufficient and that the
frozen strategy/scorer configuration is not broadly cross-asset robust.

The completed evidence is recorded in:

`docs/milestones/2026-08-14_primary8_usd100_baseline_v1.txt`

## Current research gate

The next gate is cross-asset discrimination diagnosis.

Primary question:

Why does BTC/USD survive all three frozen validation periods while the same
strategy/scorer configuration fails one or more periods on every other
PRIMARY member?

The next diagnosis should compare assets under the already frozen:

* historical-source contracts
* universe membership
* eligibility policy
* chronological folds
* scorer contract
* cost model
* equal-USD-notional sizing

Candidate explanatory dimensions include:

* entry quality
* trend persistence
* volatility structure
* scorer scaling or saturation
* early continuation
* stop/exit interaction
* market-regime compatibility

Do not begin broad parameter optimization before this contrast is understood.

The diagnosis should feed directly into the next research stages:

1. reduce the scorer/strategy parameter space using observed feature
   discrimination and structural evidence
2. define bounded common parameter ranges rather than one BTC-specific point
3. run a PRIMARY_COMPARABLE Monte Carlo or equivalent randomized search in
   which each candidate is applied unchanged across all included assets
4. evaluate cross-period and cross-asset robustness, including neighborhood
   stability rather than selecting only the highest aggregate-PnL point
5. investigate limited normalized asset/regime adjustment controls only
   after a common robust region has been established
6. use constrained independent asset searches later as a transferability
   diagnostic, not as the primary model-development path

The target is a common transferable feature structure with minimal justified
adaptation, not separate unconstrained parameter sets for every asset.

Do not inspect protected 2025+ out-of-sample data.

The exact branch, current repository checkpoint, and immediate execution plan
belong in:

`HANDOFF.md`

## Campaign metadata

Each campaign should record:

* campaign ID
* code commit
* source contract
* dataset identity
* manifest fingerprint
* symbol
* timeframe
* train and validation folds
* final test reservation
* varied parameters
* frozen parameters
* fees
* slippage
* random seed
* candidate fingerprints
* output paths
* status
* start and completion timestamps

## Candidate search mission

The first real campaign should be bounded and interpretable.

It should:

* use deterministic candidate generation
* vary only agreed parameters
* freeze all unrelated settings
* record every candidate
* preserve rejected candidates
* avoid changing the search space after seeing results
* evaluate each fold independently
* aggregate results transparently

Candidate selection should not rely only on total profit.

## Candidate evaluation mission

Candidate evaluation should include:

* out-of-sample net PnL
* maximum drawdown
* trade count
* fold consistency
* parameter stability
* cost sensitivity
* profit concentration
* loss concentration
* exposure
* unresolved positions
* operational complexity

A candidate should not advance because of one exceptional trade or one favorable period.

## Parameter stability mission

Finalists should be tested against nearby parameter values.

The project should reject configurations that:

* work only at one isolated point
* collapse under small parameter changes
* reverse behavior in neighboring settings
* depend on an unusually precise threshold

The goal is a stable region, not a lucky coordinate.

## Cost-stress mission

Finalists should be rerun with worse execution assumptions.

Stress cases may include:

* higher fees
* higher slippage
* both higher fees and slippage
* delayed entry
* less favorable stop execution

A candidate that becomes unprofitable under modest cost stress should not advance.

## Profit-concentration mission

Finalists should be tested after removing:

* best trade
* best day
* best week
* best month

The project should measure how much total performance depends on exceptional events.

A candidate should not advance when one event explains most of the profit.

## Risk-analysis mission

Risk analysis should include:

* maximum drawdown
* drawdown duration
* recovery time
* worst daily loss
* worst weekly loss
* consecutive losses
* largest single loss
* average loss
* exposure duration
* fold-specific drawdown

Risk limits must be defined before final evaluation.

## Locked final out-of-sample mission

Before running the final out-of-sample test:

* candidate is selected
* parameters are frozen
* ranking criteria are frozen
* success criteria are frozen
* cost assumptions are frozen
* code commit is recorded
* source fingerprint is recorded
* final window remains untouched

The final test should be run once for the campaign.

Possible outcomes:

* pass
* fail
* inconclusive
* invalid due to a proven implementation defect

An unfavorable result is not an implementation defect.

A failed candidate should not be retuned against the same final period.

## Paper-forward mission

A candidate that passes historical evaluation should be locked and run in paper mode.

The paper-forward stage should evaluate:

* operational stability
* decision behavior
* divergence from backtest expectations
* real-time cost assumptions
* drawdown
* trade count
* restart behavior
* state continuity
* observability

No parameter retuning should occur during the paper-forward evidence period.

The duration should depend on trade count and market exposure, not only calendar time.

## Paper-forward acceptance gates

Before moving toward live capital, the locked candidate should show:

* sufficient forward trades
* no unexplained decision divergence
* acceptable drawdown
* expected entry and exit behavior
* no unresolved state failures
* reliable runtime health
* reliable restart behavior
* stable decision and trade artifacts
* acceptable cost assumptions
* no emergency strategy changes

## Real-exchange architecture mission

Before real capital, the project needs a real-exchange execution layer.

Required capabilities include:

* authenticated exchange connection
* order submission
* order acknowledgement
* client order IDs
* duplicate-order protection
* order status tracking
* partial-fill handling
* rejection handling
* cancel handling
* retry policy
* rate-limit handling
* balance reconciliation
* position reconciliation
* restart recovery
* persistent order state
* safety controls
* operator alerts

This layer must not be treated as a small extension of PaperBroker.

Real order execution introduces different failure modes and requires explicit ownership.

## Reconciliation mission

The system must be able to compare:

* intended position
* locally recorded position
* exchange-reported position
* open orders
* fills
* balances

When reconciliation is uncertain, the safe response should be:

* stop creating new risk
* alert the operator
* preserve evidence
* require explicit recovery

## Live safety mission

Before live use, verify:

* kill switch
* halt behavior
* arm behavior
* maximum daily loss
* maximum position
* maximum order size
* stale-data handling
* stale-decision handling
* duplicate-order prevention
* restart recovery
* reconciliation failure behavior
* network failure behavior
* exchange outage behavior

Safety controls should be tested intentionally.

They should not be assumed to work because the code exists.

## Shadow live mission

Before submitted live orders, the real-exchange adapter should operate in shadow mode.

Shadow mode should:

* connect to the exchange
* read balances
* read positions
* read open orders
* generate intended orders
* record what would have been submitted
* submit no real order

This stage tests integration without creating market exposure.

## Tiny-order mission

After shadow mode passes, the system may use the exchange’s smallest practical orders.

The purpose is to verify:

* acknowledgement
* fills
* partial fills
* cancel behavior
* fees
* slippage
* reconciliation
* restart recovery
* duplicate protection
* real safety controls

The purpose is not income.

## Tiny-capital mission

Tiny capital should be financially insignificant.

It should be an amount that can be lost completely without affecting:

* housing
* food
* education
* healthcare
* emergencies
* debt payments
* family responsibilities

Tiny-capital success requires both:

* acceptable strategy behavior
* correct operational behavior

## Controlled scaling mission

Scaling should occur only after written gates are passed.

Scaling should be:

* gradual
* reversible
* risk-limited
* evidence-based
* separated by observation periods

Capital must not be increased to recover losses.

A poor result should reduce or stop exposure.

## Observability roadmap

The system should become more informative over time.

Planned observability improvements may include:

* clearer run summaries
* fold-level research reports
* candidate comparison reports
* parameter-stability views
* cost-stress summaries
* drawdown reports
* profit-concentration reports
* execution-event summaries
* unresolved-position visibility
* runtime incident records
* campaign progress reporting
* dashboard links to authoritative artifacts

The dashboard should summarize existing truth.

It should not become a separate source of truth.

## Documentation roadmap

Documentation should remain current as contracts evolve.

Expected documentation areas include:

* architecture
* research principles
* contributor onboarding
* operator procedures
* artifact schemas
* source contracts
* campaign contracts
* live-readiness gates
* incident handling
* exchange adapter behavior
* reconciliation procedures

Future behavior must be labeled as planned until implemented and verified.

## Contributor roadmap

The initial contributor model is invite-first.

New contributors should begin with:

* read access
* one bounded review
* findings before code
* one focused issue
* one small contribution
* targeted verification

Sustained contributors may eventually own areas such as:

* historical data
* research methodology
* scorer campaigns
* backtest correctness
* observability
* operations
* exchange safety
* documentation

Ownership includes responsibility for understanding and preserving contracts.

## Suggested first contributor lanes

### Research methodology

Review:

* walk-forward design
* statistical validity
* candidate selection
* robustness
* final test protection

### Data quality

Review:

* manifests
* gaps
* timestamps
* source identity
* reproducibility

### Backtest correctness

Review:

* timing
* entries
* exits
* costs
* state isolation

### Observability

Improve:

* reports
* summaries
* dashboards
* blocked reasons
* error clarity

### Operations and safety

Review:

* restarts
* controls
* reconciliation
* live-readiness gaps

### Documentation

Improve:

* onboarding
* diagrams
* terminology
* procedures
* current-state clarity

## Issues and review process

Future repository organization may include issue templates for:

* bug report
* research validity concern
* architecture proposal
* observability improvement
* documentation improvement

Substantial changes should begin with:

* problem
* evidence
* root cause
* proposed ownership
* affected files
* protected behavior
* verification plan
* risks

## Work that should wait

The following should not be prioritized yet:

* meaningful live capital
* aggressive strategy expansion
* SHORT re-enablement
* Event-Risk trade integration
* multiple exchanges
* multiple asset classes
* complex portfolio allocation
* machine-learning complexity without a clear need
* public high-volume contribution
* major framework rewrites
* large-scale cloud deployment

These areas may become appropriate later.

They should not distract from proving one trustworthy research and execution path.

## Advancement gates

The project does not advance according to a calendar estimate.

It advances only when evidence gates are satisfied.

### Research gate

Before a candidate can advance:

* ordinary validation evidence is complete
* profitability is not concentrated in one fold or exceptional trade
* drawdown is acceptable
* transaction costs are realistic
* nearby parameter behavior is stable where relevant
* cross-asset evidence is understood
* protected final out-of-sample data remains untouched

### Final out-of-sample gate

Before opening protected OOS:

* candidate is frozen
* parameters are frozen
* evaluation rules are frozen
* cost assumptions are frozen
* code identity is recorded
* source/universe identity is recorded
* success/failure criteria are frozen

The final test is evidence, not another tuning period.

### Paper-forward gate

Before meaningful execution advancement:

* historical candidate survives final OOS evaluation
* forward paper behavior is sufficiently observed
* operational stability is demonstrated
* expected and observed behavior are reasonably aligned
* risk remains acceptable

### Real-exchange gate

Before any meaningful real-money execution:

* exchange-order handling is explicitly implemented
* balance and position reconciliation exist
* partial-fill behavior is understood
* cancellation and retry behavior are verified
* restart/recovery behavior is verified
* live safety controls are independently checked
* tiny-capital testing is explicitly authorized

There is no promised schedule for these gates.

If no candidate demonstrates a robust edge, the correct outcome is to reject
the candidate or strategy family rather than advance because time has passed.
