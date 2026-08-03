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

The engineering foundation is advanced.

The project currently supports:

* historical data collection and storage
* audited Coinbase BTC/USD 5-minute history
* explicit treatment of confirmed data gaps
* gap-aware replay
* paper-broker execution
* decision and trade artifacts
* runtime health controls
* live-versus-backtest equivalence checks
* scorer research
* walk-forward research components
* an isolated Event-Risk service
* dashboard visibility
* Docker-based deployment on OLD-BOX

Profitability is not yet proven.

Meaningful live capital is not yet appropriate.

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

## Completed milestone: historical dataset audit

The main historical research dataset is:

```
coinbase_history_2022_20260209
```

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

## Current mission protected behavior

The current mission must not change:

* run_single_trial()
* run_backtest() execution behavior
* replay segmentation
* per-segment warmup
* strategy thresholds
* scorer parameters
* LONG-only policy
* SHORT quarantine
* Event-Risk isolation
* paper runtime
* fee and slippage behavior
* existing decision and trade schemas
* legacy regression behavior

## Current mission verification

Required checks include:

* LOCAL compile and import checks
* exact gap-boundary tests
* half-open fold adjacency tests
* range crossing one gap
* range crossing gaps 6 and 7
* preservation of the three-bar segment
* deterministic fold statistics
* removal of private engine imports
* small gap-crossing trial on OLD-BOX
* research execution-event artifact verification
* established legacy regression
* documentation update
* focused commit

The complete four-year backtest does not need to be rerun unless the implementation changes historical execution behavior.

## Next mission: campaign runner

After manifest-backed fold planning is complete, the next major mission is a true multi-trial campaign runner.

The campaign runner should own:

* campaign identity
* candidate generation
* source loading
* source reuse
* trial orchestration
* progress tracking
* result collection
* failure recording
* campaign summaries

The campaign runner should load and audit one historical source per campaign process.

It should then explicitly reuse that source across trials.

This optimization should not be added before the campaign runner exists.

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

## Estimated timeline

No timeline can guarantee profitability.

Assuming steady progress and no major strategy failure:

### Near term

Approximately 3 to 6 weeks:

* complete manifest-backed walk-forward planning
* define historical folds
* create campaign contracts
* prepare the first bounded campaign

### Research phase

Approximately 1 to 3 additional months:

* run campaigns
* evaluate candidates
* reject weak configurations
* test stability
* stress costs
* complete a locked final out-of-sample test

### Paper-forward phase

Approximately 2 to 4 additional months:

* run the locked candidate
* collect sufficient forward trades
* verify operational stability
* compare expected and observed behavior

### Real-exchange preparation

Approximately 1 to 2 additional months:

* build order handling
* build reconciliation
* test restarts
* test safety controls
* run shadow and tiny-order validation

A realistic planning range is:

* 6 to 12 months before tiny live capital
* 12 to 18 months or longer before meaningful capital

The timeline may be longer if no candidate passes the evidence gates.

That is an acceptable outcome.

## Readiness gates

## Research-ready

Requires:

* audited source
* explicit gap handling
* deterministic replay
* preserved legacy behavior
* reproducible artifacts

Current status:

```
substantially achieved
```

## Campaign-ready

Requires:

* public historical source contract
* half-open folds
* campaign manifest
* deterministic candidate identity
* automated result collection

Current status:

```
in progress
```

## Candidate-ready

Requires:

* multiple acceptable folds
* acceptable drawdown
* sufficient trade count
* parameter stability
* cost resilience

Current status:

```
not achieved
```

## Final-test-ready

Requires:

* selected candidate
* frozen parameters
* frozen success criteria
* untouched final period
* recorded commit and source fingerprint

Current status:

```
not achieved
```

## Paper-forward-ready

Requires:

* candidate passes final test
* runtime configuration locked
* evidence collection plan
* no unresolved execution defects

Current status:

```
not achieved
```

## Tiny-live-ready

Requires:

* paper-forward evidence
* real order adapter
* reconciliation
* restart safety
* duplicate protection
* tested loss limits
* tested kill switch
* operator alerts

Current status:

```
not achieved
```

## Meaningful-capital-ready

Requires:

* successful tiny-capital operation
* live costs inside expected range
* acceptable live drawdown
* sustained operational reliability
* predefined scaling plan
* no unresolved safety incidents

Current status:

```
not achieved
```

## Decision framework

At the end of each mission, choose one result:

* PASS
* FAIL
* PAUSE FOR MORE EVIDENCE
* INVALID DUE TO IMPLEMENTATION DEFECT
* DEFERRED

The decision should include:

* evidence
* limitations
* preserved artifacts
* next action

A mission should not silently drift into another mission.

## Roadmap maintenance

Update this roadmap when:

* a milestone passes
* a mission fails
* ownership changes
* readiness changes
* a major contract changes
* a new phase begins
* planned work is intentionally deferred

Do not mark a capability complete before it is implemented and practically verified.

## Final roadmap principle

The project should move toward real money only when the evidence and operational controls justify it.

The objective is not to reach live trading quickly.

The objective is to build a system that can tell the truth about whether live trading is justified at all.
