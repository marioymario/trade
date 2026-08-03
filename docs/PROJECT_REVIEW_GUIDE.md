# Project Review Guide

## Purpose

This guide helps invited reviewers examine the project without producing random suggestions or changing code before understanding the system.

The most useful review identifies risks that could:

* invalidate research conclusions
* create data leakage
* distort backtest results
* break reproducibility
* hide operational failures
* make future live execution unsafe
* reduce the system’s ability to explain its own behavior

The first review should normally be read-only.

## Review goals

A good review should help answer questions such as:

* Is the system producing trustworthy information?
* Are research conclusions supported by the data and execution model?
* Can hidden assumptions create false profitability?
* Are important failure states observable?
* Are responsibilities assigned to the correct modules?
* Can the system be reproduced and verified?
* Is the project becoming safer and more informative over time?

The goal is not to produce the most findings.

The goal is to improve the truthfulness, safety, reproducibility, and usefulness of the system.

## Recommended starting documents

Read these first:

* README.md
* CONTRIBUTING.md
* docs/CANONICAL_CURRENT_STATE.md
* docs/research/historical_backfill_mission_2022_2026.md

The canonical current-state document takes priority when older notes or handoffs conflict with it.

## Recommended starting code

For the gap-aware historical replay work, review:

* files/research/historical_dataset.py
* files/backtest/replay.py
* files/backtest/segment_executor.py
* files/backtest/engine.py
* files/research/execution_events.py
* files/broker/paper.py
* files/research/contracts/coinbase_history_2022_20260209_gaps.json

For scorer and walk-forward research, review:

* files/research/scorer_walk_forward.py
* files/research/scorer_trial.py
* files/research/scorer_search_config.py
* files/research/scorer_parameter_space.py
* files/research/scorer_metrics.py

For live and paper-runtime behavior, review:

* files/main.py
* files/data/features.py
* files/data/market.py
* files/data/storage.py
* files/data/decisions.py
* files/data/trades.py
* files/strategy/rules.py
* files/strategy/filters.py
* files/broker/paper.py

## Current project state

The engineering foundation is advanced enough for disciplined research.

The historical dataset and replay path have been audited across:

* 431,842 stored bars
* seven confirmed Coinbase outages
* eight physical replay segments
* 430,446 processed decision rows
* 266 historical trades

The full gap-aware historical contract passed.

Profitability is not proven.

The main research question remains:

Can any strategy and scorer configuration produce repeatable out-of-sample gains with acceptable risk after realistic costs?

## Areas already intentionally separated

Reviewers should preserve these separations unless the review specifically challenges them.

### Historical research versus paper runtime

Historical research code must not silently change paper-runtime behavior.

### Event-Risk versus trading loop

Event-Risk is intentionally isolated.

It should not be connected to entry or exit behavior without a defined research plan.

### LONG versus SHORT policy

LONG is enabled.

SHORT is quarantined.

SHORT signals remain observable, but SHORT entries remain blocked.

### New research versus frozen legacy campaigns

New manifest-backed research should use the public historical contract.

Frozen legacy campaigns should remain reproducible but should not silently become part of the new planner.

### LOCAL versus OLD-BOX

LOCAL is used for editing, Git, documentation, design, and deployment.

OLD-BOX is used for:

* historical data
* backtests
* scorer research
* runtime validation
* paper execution
* dashboard services

Data-dependent work should not be run on LOCAL.

## Review categories

Choose one bounded category for the first review.

Do not review the entire repository at once unless specifically requested.

## Research methodology

Focus on:

* train, validation, and test separation
* walk-forward split design
* data leakage
* candidate-selection bias
* minimum evidence requirements
* cost assumptions
* drawdown analysis
* parameter stability
* final untouched testing
* overfitting risk
* trade-count sufficiency
* selection of favorable periods
* repeated tuning against validation data

Questions to ask:

* Are chronological boundaries defined before results are viewed?
* Can a failed validation result be retuned against?
* Can the final test period influence candidate selection?
* Does one profitable period dominate the complete result?
* Does one trade dominate the result?
* Are nearby parameter values stable?
* Are fees and slippage realistic?
* Is the number of trades sufficient to support a conclusion?

## Historical data quality

Focus on:

* audit correctness
* timestamp rules
* gap manifest integrity
* partition validation
* duplicate handling
* missing-data policy
* source fingerprints
* reproducibility
* dataset bounds
* timeframe alignment
* source ownership

Questions to ask:

* Can missing bars be mistaken for normal market movement?
* Can a requested range begin inside a confirmed gap?
* Can a requested range end inside a confirmed gap?
* Can indicators use bars from before a gap?
* Can the same timestamp appear twice?
* Can a gap be silently ignored?
* Is the source identity recorded sufficiently?
* Can the dataset change without invalidating its fingerprint?
* Are dataset bounds represented consistently?

## Backtest correctness

Focus on:

* next-bar entry timing
* exit ordering
* stop-through behavior
* fees and slippage
* trade timestamps
* final-bar behavior
* gap boundaries
* unresolved positions
* live-versus-backtest equivalence
* cooldown behavior
* trailing-stop behavior
* duplicate trade risk

Questions to ask:

* Can a position be created without a legal next bar?
* Can an entry signal survive into a different physical segment?
* Can a normal exit be replaced by a forced boundary exit?
* Can fees or slippage be applied twice?
* Can a position cross a confirmed gap?
* Can a restart duplicate a decision or trade?
* Can the backtest see information that live execution could not see?
* Is the order of entry, stop, trail, and time-stop behavior explicit?
* Can a final unresolved position be mistaken for a closed trade?

## State isolation

Focus on whether these can leak across gaps, runs, or restarts:

* active position
* pending entry
* trailing stop
* trailing anchor
* cooldown
* indicator history
* scorer state
* decision deduplication state
* cumulative PnL
* daily counters
* runtime flags

Questions to ask:

* Which state is segment-local?
* Which state is run-level?
* Which state must survive a restart?
* Which state must never cross a gap?
* Can stale state influence a new run?
* Can cumulative accounting reset accidentally?
* Can segment-local state survive when it should be cleared?

## Scorer research

Focus on:

* parameter-space design
* frozen settings
* deterministic trial identity
* fold aggregation
* candidate ranking
* robustness checks
* use of private loaders
* campaign reproducibility
* search-space size
* parameter interactions
* campaign metadata

Questions to ask:

* Is each candidate uniquely identifiable?
* Are frozen parameters truly frozen?
* Are all varied parameters recorded?
* Are multiple configurations accidentally equivalent?
* Can a private loader bypass the public historical contract?
* Are fold results aggregated honestly?
* Can one fold dominate candidate ranking?
* Are rejected candidates preserved?
* Are random seeds fixed where needed?
* Is the campaign tied to a code commit and dataset fingerprint?

## Observability

Focus on:

* decision explanations
* blocked reasons
* trade artifacts
* research execution events
* run summaries
* error messages
* dashboard clarity
* operator diagnosis
* missing metrics
* silent failures

Questions to ask:

* Can an operator understand why an entry was blocked?
* Can a reviewer understand why a trade exited?
* Are gap-boundary events visible?
* Are unresolved positions visible?
* Are stale data conditions visible?
* Can a failed audit be distinguished from an empty dataset?
* Can a contributor locate the relevant artifacts easily?
* Are important warnings machine-readable?
* Does the dashboard summarize the same truth as the underlying artifacts?

## Operational safety

Focus on:

* restart behavior
* duplicate-order prevention
* kill switches
* stale state
* loss limits
* balance reconciliation
* position reconciliation
* partial fills
* failed cancels
* exchange outages
* process failure
* network failure
* stale market data
* inconsistent exchange state

Questions to ask:

* Can the system reconcile its state with an exchange?
* What happens after a process restart?
* What happens when an order is partially filled?
* What happens when an order is rejected?
* Can a cancel request fail silently?
* Can the kill switch stop new risk reliably?
* Are stale data and stale decisions detected?
* Can duplicate orders be submitted after a retry?
* Can a local position disagree with the exchange?
* Are daily and total loss limits enforced independently?

## Documentation and onboarding

Focus on:

* missing context
* unclear terminology
* outdated instructions
* duplicated truth
* inconsistent path names
* unclear ownership
* missing contributor guidance
* incomplete examples
* undocumented assumptions

Questions to ask:

* Can a new contributor understand the purpose of the project?
* Is the current state clearly separated from future plans?
* Are proven facts separated from goals?
* Are old and current workflows distinguishable?
* Are commands labeled LOCAL or OLD-BOX?
* Are public interfaces documented?
* Are important artifacts and paths discoverable?
* Do multiple documents contradict each other?
* Is the canonical source of truth clear?

## Reporting findings

Use the following format for each finding.

### Title

A short and specific description of the issue.

### Severity

Use one of:

* Critical
* High
* Medium
* Low

### Classification

Use one of:

* Confirmed defect
* Plausible risk
* Open question
* Design preference

### Affected area

Identify:

* files
* functions
* modules
* artifacts
* commands
* workflow
* runtime behavior

### Evidence

Explain what supports the finding.

Include:

* file paths
* function names
* relevant contracts
* command output
* artifact observations
* reproducible behavior

Do not present a preference as evidence.

### Potential impact

Explain what could go wrong.

Examples:

* false research conclusion
* data leakage
* incorrect trade accounting
* state leakage
* unsafe runtime behavior
* broken reproducibility
* confusing observability
* unnecessary maintenance burden

### Suggested verification

Explain what test, inspection, or reproduction would prove or disprove the concern.

### Suggested ownership

Identify which module or layer should own the fix.

### Possible direction

Provide a concise direction.

Do not produce a large implementation unless requested.

## Severity guidance

## Critical

Could cause:

* unsafe live behavior
* uncontrolled orders
* hidden data leakage
* false profitability conclusions
* corrupted trade accounting
* loss of operational control
* exposure beyond defined limits

## High

Could cause:

* materially incorrect results
* broken reproducibility
* invalid split construction
* major state leakage
* invalid risk conclusions
* incorrect execution ordering
* unreliable research artifacts

## Medium

Could cause:

* maintenance problems
* observability gaps
* inefficient workflows
* difficult diagnosis
* incomplete testing
* unclear ownership
* avoidable contributor confusion

## Low

Could improve:

* naming
* organization
* onboarding
* clarity
* limited-scope quality
* documentation consistency

## Distinguishing findings

Reviewers must separate these categories carefully.

### Confirmed defect

A problem supported by direct evidence or reproduction.

Example:

A requested start timestamp inside a confirmed gap is accepted and produces an invalid replay range.

### Plausible risk

A failure mode that appears possible but has not been proven.

Example:

A restart may preserve cooldown state incorrectly, but no reproduction has been run.

### Open question

A contract or intention is unclear.

Example:

It is unclear whether unresolved final positions should be included in summary metrics.

### Design preference

A possible improvement that is not required for correctness.

Example:

A reviewer prefers a different class name or directory layout.

Design preferences should not be presented as defects.

## What not to do during review

Do not:

* rewrite modules before discussing findings
* change strategy thresholds
* change scorer parameters
* move validation or test windows
* add a fallback path
* connect Event-Risk
* re-enable SHORT
* introduce a new framework
* add a public API without a real caller
* run data-dependent work on LOCAL
* submit bulk generated code
* treat personal preference as a confirmed defect
* combine unrelated findings into one large proposed rewrite
* assume a file is unused without checking callers
* assume an interface without inspecting it
* alter paper-runtime behavior during research work

## Review workflow

A first review should follow this sequence:

1. Read the welcome and current-state documents.
2. Select one bounded review category.
3. Identify the relevant files and contracts.
4. Inspect before proposing changes.
5. Separate defects, risks, questions, and preferences.
6. Rank findings by severity.
7. Include evidence and file references.
8. Suggest verification before implementation.
9. Discuss findings with the project owner.
10. Select one issue for possible contribution.

## Suggested first review assignments

## Gap-aware replay review

Review whether state, indicators, entries, exits, or accounting can cross a confirmed outage.

Focus on:

* physical segmentation
* warmup
* final-bar entries
* forced exits
* state reset
* event artifacts

Deliver:

* ranked findings
* file references
* failure modes
* suggested verification

Do not modify code.

## Walk-forward validity review

Review:

* split definitions
* private loader dependencies
* gap awareness
* half-open ranges
* train and validation separation
* fold statistics
* final test protection
* campaign identity

Deliver:

* confirmed issues
* leakage risks
* unclear contracts
* recommended verification

Do not modify code.

## Trade-accounting review

Review:

* fee application
* slippage application
* realized PnL
* cumulative PnL
* stop prices
* exit timestamps
* duplicate closing risk
* unresolved positions

Deliver:

* accounting invariants
* suspected failure cases
* suggested deterministic tests

Do not modify code.

## Historical-data review

Review:

* partition layout
* manifest contents
* gap definitions
* timestamp bounds
* cadence validation
* duplicate protection
* source fingerprinting

Deliver:

* data-contract findings
* missing checks
* reproducibility concerns

Do not modify code.

## Live-readiness review

Review the gap between paper execution and safe real-exchange execution.

Focus on:

* order lifecycle
* acknowledgement
* partial fills
* cancel behavior
* reconciliation
* restart recovery
* duplicate protection
* loss limits
* alerting

Do not add a live adapter during the first review.

## Observability review

Review whether the system explains its behavior clearly.

Focus on:

* decisions
* trades
* blocked reasons
* event artifacts
* run summaries
* dashboard
* error messages

Deliver:

* information gaps
* confusing fields
* missing relationships
* recommended summaries

Do not redesign the entire dashboard during the first review.

## Documentation review

Review whether a new contributor can understand:

* project purpose
* current status
* architecture
* workflow
* protected behavior
* research rules
* next mission

Deliver:

* contradictions
* missing context
* unclear terminology
* outdated instructions
* suggested small improvements

## Review outcome

A useful review may conclude:

* no defect found
* verification is sufficient
* a concern needs a targeted test
* documentation is missing
* ownership should be clarified
* a future feature should wait
* a proposed change is unnecessary
* the strategy should not advance
* the current evidence is insufficient

A review does not need to produce code to be valuable.

A careful decision not to change the system may be the correct outcome.
