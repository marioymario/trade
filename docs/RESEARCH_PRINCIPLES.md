# Research Principles

## Purpose

This document defines the research standards used to evaluate strategies, scorers, parameters, and execution behavior.

The purpose of the research process is not to prove that a strategy works.

The purpose is to determine, as honestly as possible, whether a strategy has a repeatable and risk-controlled edge after realistic costs.

A valid research outcome may be:

* advance the candidate
* collect more evidence
* revise the hypothesis
* reject the candidate
* reject the strategy family
* conclude that the available evidence is insufficient

Rejecting a weak strategy before money is placed at risk is a successful research outcome.

## Primary objective

The project’s primary research objective is:

Find a robust combination of strategy and scorer parameters that produces repeatable out-of-sample gains with acceptable risk after realistic fees and slippage.

The project does not optimize for the highest in-sample profit.

The project prioritizes:

* out-of-sample profitability
* risk control
* parameter stability
* reproducibility
* realistic execution
* sufficient trade count
* resilience across market regimes
* honest rejection of weak candidates

## What counts as evidence

Strong evidence includes:

* results from locked out-of-sample periods
* consistent behavior across multiple chronological folds
* performance that survives higher cost assumptions
* stable behavior across nearby parameter values
* sufficient trade count
* controlled drawdown
* reproducible artifacts
* consistent paper-forward behavior
* agreement between research assumptions and runtime behavior

Weak evidence includes:

* one profitable period
* one unusually profitable trade
* one favorable market regime
* high in-sample profit
* visual chart quality without statistical support
* a candidate selected after repeated retuning
* results that depend on one exact parameter combination
* results that disappear under modestly higher costs
* results with very few trades

## Research must be chronological

Trading research must respect time order.

Future information must not influence earlier decisions.

The research process should use chronological windows such as:

* training
* validation
* final out-of-sample test
* forward paper test

Randomly shuffling time-series bars is not an acceptable substitute for chronological validation.

## Train, validation, and test separation

Each research campaign should define its time windows before results are viewed.

### Training window

Used to:

* fit models
* search parameters
* identify candidates
* develop hypotheses

### Validation window

Used to:

* compare candidates
* reject unstable configurations
* evaluate robustness
* select finalists

### Final out-of-sample window

Used only after the candidate and evaluation rules are locked.

It should not be used to:

* tune parameters
* change thresholds
* modify the search space
* revise the candidate-ranking formula
* redefine success criteria

If the final out-of-sample test fails, the candidate fails that campaign.

The failed final period must not become a new tuning period for the same campaign.

## Walk-forward research

Walk-forward research should use multiple chronological folds.

A typical fold contains:

* a training interval
* a following validation interval

Later folds move forward in time.

The purpose is to test whether a candidate behaves consistently across changing market conditions.

Fold definitions should be frozen before campaign execution.

New manifest-backed fold definitions should use half-open ranges:

```
[start_ts_ms, end_ts_ms_exclusive)
```

This matches the historical dataset and gap contracts.

## Half-open range principle

Half-open ranges provide clear ownership of interval boundaries.

For adjacent windows:

```
first window:  [A, B)
second window: [B, C)
```

This prevents:

* overlap
* duplicate bars
* artificial end-of-day timestamps
* timeframe-specific final-bar calculations

A requested start must correspond to a valid available bar.

A requested end-exclusive may equal the first missing timestamp at the start of a gap.

## Gap-aware research

Confirmed historical gaps must remain explicit.

The system must not:

* synthesize missing candles
* interpolate missing prices
* substitute another exchange
* treat a gap as a normal return
* calculate indicators across a gap
* carry positions across a gap without explicit policy
* silently ignore a gap in fold planning

A research range may cross a complete confirmed gap.

When it does:

* the range resolves into multiple physical segments
* indicators warm independently in each segment
* state does not cross the gap
* post-gap decision eligibility begins only after post-gap warmup

A requested boundary inside a confirmed gap must fail clearly.

## Historical source integrity

Each research campaign should record the identity of its historical source.

Source identity should include:

* data tag
* exchange
* symbol
* timeframe
* dataset bounds
* stored-bar count
* gap manifest
* manifest fingerprint
* physical segment count

A source fingerprint must be deterministic.

It should not depend on volatile values such as file modification time.

If the historical source changes, the campaign identity should change.

## Reproducibility

A research result is incomplete unless it can be reproduced.

Each campaign should record:

* code commit
* campaign identifier
* candidate identifier
* source contract
* dataset fingerprint
* timeframe
* symbol
* train and validation windows
* final test window
* fees
* slippage
* strategy configuration
* scorer configuration
* varied parameters
* frozen parameters
* random seed where applicable
* output paths
* fold metrics
* aggregate metrics

The same inputs should produce the same outputs.

## Candidate identity

Every candidate must have a stable and unique identity.

Candidate identity should be derived from:

* all varied parameters
* all frozen behavior that affects results
* campaign identity
* source identity
* relevant execution assumptions

Two candidates with identical effective behavior should not be treated as different merely because of naming differences.

Fingerprints should be deterministic and based on canonical serialized values.

## Frozen parameters

Parameters outside the active search space must remain frozen.

A campaign should explicitly record:

* parameters being varied
* permitted values or ranges
* parameters held constant
* default values
* code version

Unrecorded parameter changes invalidate comparisons.

## Parameter search design

Search spaces should be:

* bounded
* documented
* deterministic
* large enough to test meaningful alternatives
* small enough to interpret

The project should avoid:

* extremely broad unconstrained searches
* arbitrary parameter ranges
* excessive precision without justification
* hidden parameter interactions
* changing the search space after seeing results

Search design should reflect a research hypothesis.

## Parameter stability

A strong candidate should not depend on one exact parameter value.

Nearby configurations should produce broadly similar behavior.

A candidate is suspicious when:

* a small parameter change causes performance collapse
* only one isolated point is profitable
* neighboring configurations produce opposite behavior
* one exact threshold captures a small number of lucky trades

Stability analysis should compare the candidate with nearby parameter configurations.

## Candidate ranking

Candidates should not be ranked only by total profit.

Ranking should consider:

* out-of-sample net PnL
* maximum drawdown
* trade count
* profit concentration
* fold consistency
* parameter stability
* cost sensitivity
* loss concentration
* exposure
* unresolved positions
* operational complexity

A candidate with lower profit and substantially better stability may be preferable to a high-profit unstable candidate.

## Fold aggregation

Aggregate metrics must not hide weak folds.

Research summaries should show:

* each fold separately
* aggregate result
* best fold
* worst fold
* fold trade count
* fold drawdown
* fold profitability
* cost sensitivity

A candidate should not pass only because one fold offsets several weak folds.

## Trade-count sufficiency

A result based on too few trades is uncertain.

The project should define minimum trade-count requirements before candidate selection.

Trade count should be reviewed:

* per fold
* in aggregate
* by market regime
* by side
* by exit type

A candidate with high profit from a small number of trades should not automatically advance.

## Profit concentration

Research should test whether the result depends excessively on:

* one trade
* one day
* one week
* one month
* one market event
* one regime

Useful checks include:

* remove the best trade
* remove the best day
* compare results without the best period
* calculate contribution concentration
* inspect cumulative PnL shape

A candidate that fails after removing one exceptional event is not robust.

## Drawdown

Drawdown is a primary evaluation metric.

Research should report:

* maximum drawdown
* drawdown duration
* recovery time
* worst daily loss
* worst weekly loss
* consecutive losses
* average loss
* largest loss
* drawdown by fold

Profit without acceptable drawdown is not sufficient.

Risk limits should be defined before final evaluation.

## Costs

All research must include realistic costs.

At minimum:

* exchange fees
* slippage

Where applicable, also consider:

* spread
* partial fills
* market impact
* order rejection
* latency
* funding
* borrowing costs
* minimum order size

Finalists should be re-evaluated under worse cost assumptions.

A candidate that becomes unprofitable under a modest cost increase is weak.

## Execution realism

The backtest must not assume information unavailable at decision time.

Execution assumptions should match the intended runtime as closely as practical.

Important behaviors include:

* closed-bar decisions
* next-bar entry
* stop-through handling
* trailing-stop ordering
* cooldown
* fee application
* slippage application
* final-bar entry cancellation
* gap-boundary behavior

Differences between backtest and paper runtime must be documented and tested.

## Live-versus-backtest equivalence

The project should compare live-paper and backtest decisions over the same bars.

Equivalence checks should examine:

* timestamps
* market state
* entry intent
* exit intent
* positions
* stop behavior
* trades
* costs
* blocked reasons

Differences must be explained.

Unexplained differences weaken the validity of historical conclusions.

## Strategy changes

A strategy change must begin with a written hypothesis.

The proposal should explain:

* expected behavior
* why the change may help
* affected market conditions
* risks
* development window
* validation plan
* behavior that must remain unchanged

Strategy changes must not be mixed into unrelated engineering work.

## Scorer changes

Scorer changes should define:

* features used
* weights varied
* floors varied
* penalties varied
* fixed values
* expected effect
* search range
* validation criteria

Scorer improvement is not proven by higher training profit alone.

## LONG and SHORT research

LONG and SHORT behavior should be evaluated independently where appropriate.

Current runtime policy:

* LONG enabled
* SHORT quarantined
* SHORT signals observable
* SHORT entries blocked

SHORT should not be re-enabled because of a few profitable historical examples.

Re-enablement requires a separate written research case and strong out-of-sample evidence.

## Event-Risk research

Event-Risk is currently an independent artifact.

It should not be connected directly to trading behavior until its value is tested.

A future Event-Risk study should define:

* hypothesis
* source contract
* freshness rules
* status behavior
* reason-code interpretation
* train and validation windows
* comparison baseline
* failure behavior

Event-Risk should first be tested as an independent filter or feature.

It should not introduce a direct network dependency into the trading loop.

## Baselines

Each major research change should have a baseline.

A baseline may include:

* decisions
* trades
* normalized artifact hashes
* metrics
* configuration
* code commit
* dataset identity

A new implementation should be compared against the baseline when behavior is intended to remain unchanged.

## Legacy research

Legacy campaigns may remain frozen for reproducibility.

They should be explicitly identified.

Example source contracts:

```
manifest_backed_v1
legacy_frozen_2026_v1
```

New generic research should not silently fall back to legacy behavior.

Legacy campaigns should not be reinterpreted as if they used newer contracts.

## Final out-of-sample test

Before the final test:

* candidate is selected
* parameters are frozen
* ranking rules are frozen
* success criteria are frozen
* cost assumptions are frozen
* code commit is recorded
* dataset identity is recorded

The final test should be run once for the campaign.

Possible outcomes:

* pass
* fail
* inconclusive due to insufficient evidence
* invalid due to a proven implementation defect

An implementation defect may justify rerunning after correction.

An unfavorable result does not.

## Forward paper testing

A candidate that passes historical evaluation should run forward in paper mode.

Forward paper testing should use:

* the locked candidate
* no parameter retuning
* the same execution assumptions
* the same risk limits
* real-time market conditions

The duration should be based on evidence and trade count, not only calendar time.

A low-frequency strategy may require several months.

## Paper-forward acceptance

Before moving toward live capital, paper-forward testing should demonstrate:

* operational stability
* expected decision behavior
* no unexplained divergence from research
* acceptable drawdown
* acceptable cost assumptions
* sufficient trade count
* no unresolved state failures
* reliable restart behavior
* clear observability

## Tiny live-capital principle

Historical and paper performance do not guarantee live performance.

The first live stage should use financially insignificant capital.

The purpose of tiny live capital is to test:

* exchange authentication
* order acknowledgement
* fills
* partial fills
* cancellations
* reconciliation
* duplicate protection
* restart recovery
* real costs
* kill switches
* loss limits

The purpose is not income.

## Scaling principle

Capital should increase only after predefined gates are passed.

Scaling should be:

* gradual
* reversible
* risk-limited
* evidence-based

Capital must not be increased to recover losses.

A poor result should reduce or stop exposure, not increase it.

## Research acceptance gates

A candidate should not advance unless it passes written gates.

Suggested categories include:

### Profitability

* positive aggregate out-of-sample net PnL
* positive performance in multiple folds
* no dependence on one exceptional trade or period
* acceptable performance under worse costs

### Risk

* maximum drawdown within limit
* largest loss within limit
* daily loss within limit
* consecutive-loss behavior understood
* exposure bounded

### Robustness

* nearby parameters remain reasonable
* multiple folds remain acceptable
* best-trade removal does not destroy the result
* cost stress does not destroy the result
* trade count is sufficient

### Reproducibility

* same inputs reproduce the same artifacts
* commit recorded
* source fingerprint recorded
* configuration recorded
* output paths isolated

### Forward paper behavior

* locked candidate runs without retuning
* runtime remains healthy
* behavior matches expectations
* sufficient forward evidence exists

## Reasons to reject a candidate

A candidate should be rejected when:

* it fails locked out-of-sample testing
* it depends on one trade or period
* it collapses under nearby parameters
* it becomes unprofitable under modest cost stress
* it has insufficient trade count
* drawdown exceeds the predefined limit
* results cannot be reproduced
* execution assumptions are unrealistic
* live-paper behavior diverges without explanation
* state or accounting defects invalidate the result

## Inconclusive results

Not every result is a pass or fail.

A result may be inconclusive because:

* trade count is too low
* the evaluation period is too short
* one market regime dominates
* operational evidence is incomplete
* cost assumptions remain uncertain

An inconclusive result should not be treated as success.

The appropriate action may be to collect more data without changing the candidate.

## Research reporting

A research report should include:

* objective
* hypothesis
* source identity
* code commit
* campaign identity
* split definitions
* candidate parameters
* frozen parameters
* execution assumptions
* fold metrics
* aggregate metrics
* drawdown
* trade count
* cost stress
* parameter stability
* limitations
* decision
* artifact paths

Reports should distinguish:

* observed facts
* calculations
* interpretations
* assumptions
* recommendations

## Research decisions

Each campaign should end with a clear decision.

Examples:

* reject
* hold for more evidence
* advance to final test
* advance to paper forward test
* return to engineering due to invalid execution assumptions

The decision should explain why.

## What research must not become

The project must avoid:

* repeated tuning until profit appears
* moving windows after seeing results
* selecting metrics after the outcome is known
* hiding losing folds
* ignoring costs
* ignoring drawdown
* treating paper results as guaranteed
* treating one successful campaign as permanent proof
* changing strategy behavior during infrastructure tests
* using complexity to hide uncertainty

## Research principle summary

The project should advance only when the evidence becomes stronger.

The project should stop or reject a candidate when the evidence becomes weaker.

The correct goal is not to make the strategy look profitable.

The correct goal is to learn whether it is actually robust enough to deserve further risk.
