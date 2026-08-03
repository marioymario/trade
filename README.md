# Trading Research and Paper Execution System

## Project status

This project is an active trading-research and paper-execution system.

Its purpose is to determine whether a trading strategy can demonstrate a repeatable, risk-controlled edge under realistic historical and forward-testing conditions.

The infrastructure is operational, but profitability has not been proven.

The current priority is improving:

* research quality
* data integrity
* reproducibility
* backtest correctness
* observability
* risk controls
* paper-to-live readiness

The project is not ready for meaningful real-money execution.

A valid outcome may be that a strategy should not be traded. Rejecting a weak or unstable strategy before money is placed at risk is part of the project’s purpose.

## What this project is trying to solve

Trading systems can appear profitable for the wrong reasons, including:

* overfitting
* data leakage
* unrealistic execution assumptions
* incorrect handling of missing data
* unstable parameter choices
* insufficient trade count
* selection of favorable market periods
* hidden differences between backtest and live behavior
* unrealistic fees or slippage
* repeated tuning against validation or test data

This project aims to identify and reduce those risks honestly and reproducibly.

The goal is not to produce the highest historical return.

The goal is to determine whether any strategy or scorer configuration can produce repeatable out-of-sample gains with acceptable risk after realistic costs.

## Current capabilities

The system currently includes:

* Coinbase BTC/USD 5-minute historical data
* an audited historical dataset covering 2022 through early 2026
* explicit handling of seven confirmed Coinbase data outages
* gap-aware historical replay
* independent indicator warmup after data gaps
* paper-broker execution modeling
* next-bar entry modeling
* trailing-stop behavior
* cooldown behavior
* decision and trade artifacts
* strict research execution-event artifacts
* live-versus-backtest equivalence tooling
* restart-safe decision deduplication
* paper-runtime health checks
* STOP, HALT, and ARM controls
* scorer research infrastructure
* walk-forward research components
* an isolated Event-Risk service
* Docker-based runtime services
* a Streamlit dashboard
* reproducible deployment to the execution machine

The gap-aware historical replay implementation is recorded in commit:

```
d4c6f7d Add gap-aware historical replay
```

## What is not yet proven

The project has not yet proven:

* a repeatable trading edge
* positive performance across locked out-of-sample windows
* acceptable drawdown across different market regimes
* stability across nearby parameter values
* reliable performance under worsened cost assumptions
* sufficient forward paper-trading evidence
* safe real-exchange order handling
* readiness for meaningful capital

No contributor should describe this repository as a profitable trading system or a finished trading product.

## Current research direction

The next major research mission is to move walk-forward scorer planning fully onto the public manifest-aware historical contract.

The intended design includes:

* a public audited historical research-source contract
* half-open research windows
* explicit gap-boundary validation
* fold planning through the existing segmentation machinery
* deterministic fold statistics
* separation between manifest-backed research and frozen legacy campaigns
* removal of private engine-loader dependencies from scorer walk-forward planning

Trial execution should continue through the existing public backtest path.

## Historical dataset

The main audited historical research dataset is:

* exchange: Coinbase
* symbol: BTC/USD
* timeframe: 5 minutes
* interval: January 1, 2022 through February 8, 2026
* stored bars: 431,842
* confirmed missing bars: 158
* confirmed outages: 7
* physical replay segments: 8

No synthetic candles were created.

No data from another exchange was inserted into the Coinbase dataset.

Missing intervals are represented explicitly through a versioned gap manifest.

## Gap-aware replay

The historical replay system treats each continuous section of data as an independent physical segment.

The replay contract prevents:

* indicators from warming across confirmed outages
* positions from crossing confirmed outages
* pending entries from crossing confirmed outages
* trailing-stop state from crossing confirmed outages
* cooldown state from crossing confirmed outages

At every post-gap segment, features and warmup begin independently.

Short physical segments remain visible even when they are too short to produce decisions.

The full four-year gap-aware run completed successfully with:

* 431,842 total stored bars
* 430,446 processed decision rows
* 266 closed trades
* no decisions inside confirmed gaps
* no trade timestamps inside confirmed gaps
* no duplicate decision timestamps

## System boundaries

The project has separate operational layers.

### Historical research layer

This layer owns:

* historical data validation
* gap manifests
* replay segmentation
* backtests
* scorer research
* walk-forward planning
* research artifacts
* candidate evaluation

### Paper runtime layer

This layer owns:

* live market-data polling
* closed-bar decisions
* paper positions
* operational controls
* runtime health
* dashboard visibility

Historical research changes must not silently alter paper-runtime behavior.

### Event-Risk service

Event-Risk is intentionally separate from the trading loop.

It produces independent processed artifacts for later research.

It must not affect entries, exits, or paper-runtime behavior until its value has been tested through a defined research plan.

## Current trading policy

The current paper-runtime policy is:

* LONG enabled
* SHORT quarantined
* SHORT signals remain observable
* SHORT entries remain blocked
* Event-Risk remains disconnected from trade decisions

These policies must not be changed casually or as part of unrelated work.

## Machine roles

### LOCAL

Repository:

```
/home/gto5080/Projects/trade
```

LOCAL is used for:

* source editing
* Git
* documentation
* research design
* deployment

LOCAL is not used for:

* historical backtests
* data-dependent validation
* scorer execution
* production-like runtime testing

### OLD-BOX

Repository and runtime directory:

```
/home/kk7wus/Projects/trade
```

OLD-BOX is used for:

* historical data storage
* backtests
* scorer research
* paper runtime
* dashboard
* Jupyter
* operational tools

Git truth exists on LOCAL and GitHub.

OLD-BOX is an execution machine, not the source-control authority.

## Deployment

The canonical deployment command from LOCAL is:

```
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh
```

Deployment uses rsync and preserves runtime-owned data and configuration.

Source code should not be edited directly on OLD-BOX.

## Project architecture

Important modules include:

### Historical data

```
files/research/historical_dataset.py
```

Owns:

* manifest loading
* full historical audit
* physical segmentation
* range validation
* warmup-safe slicing

### Replay planning

```
files/backtest/replay.py
```

Owns:

* replay-segment contracts
* replay-plan construction
* translation from resolved historical datasets into executable replay plans

### Segment execution

```
files/backtest/segment_executor.py
```

Owns:

* execution of one replay segment
* feature calculation
* market-state evaluation
* entry and exit evaluation
* boundary action facts

### Backtest engine

```
files/backtest/engine.py
```

Owns:

* run-level orchestration
* source selection
* segment ordering
* boundary classification
* result aggregation
* research-event sequencing

### Paper broker

```
files/broker/paper.py
```

Owns:

* paper positions
* entry and exit execution
* costs
* cooldown
* trailing state
* cumulative realized PnL
* boundary-safe state reset

### Research execution events

```
files/research/execution_events.py
```

Owns:

* strict research event schema
* event validation
* deterministic event serialization

## Important project documents

Start with:

* README.md
* CONTRIBUTING.md
* docs/PROJECT_REVIEW_GUIDE.md
* docs/CANONICAL_CURRENT_STATE.md
* docs/research/historical_backfill_mission_2022_2026.md

The canonical current-state document takes priority when older handoffs or notes conflict with it.

## Contribution model

This project currently uses an invite-first contribution model.

The project owner is looking for:

* thoughtful review
* sustained one-to-one collaboration
* evidence-based engineering
* clearly owned work
* contributors willing to understand the system before changing it
* improvements that make the system more trustworthy and informative

The project is not currently seeking:

* random feature suggestions
* unsolicited large rewrites
* bulk AI-generated pull requests
* strategy changes based only on intuition
* speculative refactoring
* changes that bypass existing architecture
* contributions aimed only at adding complexity
* automated submissions that the contributor cannot explain

Substantial changes should be discussed before implementation.

See CONTRIBUTING.md for the full process.

## Useful contribution areas

Potential contribution areas include:

* research methodology
* backtest correctness
* historical data quality
* statistical validation
* observability and reporting
* paper-runtime safety
* exchange execution readiness
* documentation and onboarding
* testing and reproducibility
* dashboard clarity
* research result interpretation

New contributors should begin with a bounded review task before changing code.

## Review before code

A useful first contribution is usually a review, not a patch.

Reviewers should separate findings into:

* confirmed defects
* plausible risks
* open questions
* design preferences

These categories should not be mixed together.

Findings should include:

* severity
* affected file or workflow
* evidence
* possible impact
* suggested verification
* suggested ownership

## Strategy protection

Strategy behavior is not changed casually.

The following require evidence and explicit agreement:

* entry thresholds
* exit thresholds
* scorer parameters
* cooldown behavior
* trailing-stop behavior
* position sizing
* LONG or SHORT policy
* Event-Risk integration
* validation boundaries
* final out-of-sample boundaries

Strategy changes require a written hypothesis and a defined verification plan.

Failed validation or final out-of-sample results must not be repaired by retuning against the same period.

## Research principles

The project prioritizes:

* out-of-sample evidence
* realistic costs
* controlled drawdown
* parameter stability
* reproducibility
* sufficient trade count
* chronological testing
* honest rejection of weak candidates

The project does not prioritize:

* maximum in-sample profit
* one unusually successful period
* one unusually successful trade
* attractive charts without statistical support
* repeated tuning until a desired answer appears

## Current readiness

The system is currently suitable for:

* historical research
* deterministic gap-aware backtests
* scorer research development
* paper execution
* observability improvements
* operational safety development
* contributor review

The system is not currently suitable for:

* relying on trading for income
* meaningful personal capital
* unsupervised live execution
* rapid scaling
* assuming historical performance will continue

## Path toward live capital

The expected progression is:

1. Complete manifest-backed walk-forward planning.
2. Define locked chronological research folds.
3. Run deterministic scorer campaigns.
4. Reject unstable or overfit candidates.
5. Run a final untouched out-of-sample test.
6. Forward-test a locked candidate in paper mode.
7. Build real-exchange order handling and reconciliation.
8. Validate kill switches and loss limits.
9. Begin only with financially insignificant capital.
10. Scale only after predefined evidence gates are passed.

The expected timeline is uncertain.

A reasonable planning range is approximately:

* 6 to 12 months before tiny live capital
* 12 to 18 months or longer before meaningful capital

The calendar alone does not determine readiness.

Evidence does.

## License

This project is licensed under the MIT License.

The license allows reuse, modification, and distribution subject to the license terms.

The contribution process described in this repository is a project-governance policy. It does not reduce or replace the rights granted by the MIT License.

## Important disclaimer

This repository is for research and engineering purposes.

It is not financial advice.

Historical or paper-trading performance does not guarantee future results.

Do not risk money needed for:

* housing
* food
* education
* healthcare
* emergencies
* debt payments
* family responsibilities

Any future live use should begin with capital that can be lost completely without affecting personal or family finances.
