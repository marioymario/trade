# Deterministic Scorer Campaign Runner Contract

## 1. Status and ownership

Contract status:
IMPLEMENTED AND ACTIVE

Active authoritative research path:
manifest-backed deterministic scorer campaigns

Current implementation versions:

* campaign schema version: 6
* trial-space version: scorer_parameter_space_v2_normalized_slope
* execution artifact contract: scorer_execution_artifacts_v2
* rejection policy: scorer_rejection_policy_v3
* ranking policy: scorer_ranking_policy_v1

Implemented prerequisites include:

* public HistoricalResearchSource
* manifest-backed gap-aware replay
* half-open chronological walk-forward planning
* deterministic fold statistics
* deterministic scorer trials
* isolated campaign artifacts
* resume and identity validation
* aggregation
* rejection and ranking policy

The campaign runner does not replace or retire:

* the low-level single-trial scorer utility
* automatic manifest-backed backtests
* legacy Parquet backtests
* frozen legacy research paths

Those paths remain available for compatibility and regression work.

The campaign runner is the stricter research orchestration path.

It must never silently fall back to a legacy or live-data namespace.

## 2. Mission

The campaign runner executes a deterministic bounded scorer search across the
frozen chronological walk-forward folds using one audited historical source.

The primary objective is repeatable positive out-of-sample performance with
controlled risk.

The campaign must not rank candidates by total in-sample profit alone.

## 3. Source contract

Required source contract: manifest_backed_v1

At process start, the campaign runner must:

1. Load its explicit campaign configuration.
2. Require manifest_backed_v1.
3. Resolve and audit exactly one HistoricalResearchSource.
4. Verify the requested data tag, symbol, and timeframe.
5. Record the manifest path and manifest fingerprint.
6. Reuse the exact resolved source object for planning and trial execution.

The campaign must fail before trial execution when the source cannot be
resolved or audited.

The campaign must not:

- derive DATA_TAG implicitly from CCXT_EXCHANGE
- select the live paper namespace
- rediscover the manifest separately for every trial
- invoke the backtest engine's legacy fallback
- mix data from another exchange
- fabricate missing bars

The existing backtest engine fallback remains preserved for non-campaign
compatibility paths.

## 4. Campaign inputs

An immutable campaign specification contains the effective
behavior-changing campaign assumptions, including:

* campaign_schema_version
* source_contract
* data_tag
* symbol
* timeframe
* scorer_contract
* trial_space_version
* trial_count
* random_seed
* resolved walk-forward splits
* fixed strategy settings
* minimum total trades
* minimum validation trades per split
* min_bars
* cooldown_bars
* max_order_size
* cost scenarios

The specification may additionally contain:

* research_order_notional_usd

research_order_notional_usd is optional and research-only.

When absent:

* legacy/default sizing behavior remains unchanged
* the field is not serialized into the legacy campaign specification
* historical default campaign identity remains stable

When supplied:

* the value must be positive
* research execution derives entry quantity from explicit USD notional
* the value becomes part of serialized campaign identity
* semantically different sizing assumptions therefore receive different
  campaign IDs

The sizing override must not silently alter live sizing behavior.

All effective campaign values must be frozen in the campaign manifest.

The protected final out-of-sample window is not part of ordinary candidate
selection.

It remains locked until the research-selection policy explicitly authorizes
its use.

## 5. Identity rules

The effective immutable campaign specification is serialized as canonical
JSON with deterministic key ordering and values suitable for stable hashing.

The campaign ID is deterministic for the effective specification, Git/source
identity, resolved folds, and candidate set.

Campaign ID format:

scorer_campaign_<deterministic hexadecimal suffix>

Campaign identity must capture every behavior-changing assumption that can
materially affect research results.

Identity includes, as applicable:

* campaign schema version
* Git commit
* source contract
* manifest fingerprint
* data tag
* symbol
* timeframe
* resolved walk-forward definitions
* scorer contract
* trial-space version
* candidate identities
* fixed strategy settings
* fees and slippage
* minimum trade requirements
* cost scenarios
* explicit research sizing assumptions

The existing deterministic trial_id remains the scorer-candidate identity.

research_order_notional_usd has special compatibility semantics:

* when None, it is omitted from serialized specification identity so existing
  legacy/default campaign identities remain stable
* when explicitly supplied, it is serialized and therefore produces a
  different campaign identity

Campaign execution must never reuse artifacts from a semantically different
campaign merely because the scorer candidate is identical.

Every candidate/window execution must retain a stable execution identity
derived from its campaign, trial, fold, phase, and cost scenario.

## 6. Source and fold ownership

The campaign entry point owns:

- historical source resolution
- source auditing
- source fingerprint recording
- walk-forward split resolution
- candidate generation
- deterministic execution-plan construction

Trial execution receives:

- the already-resolved historical source
- the already-resolved window definition
- the deterministic candidate
- an explicit immutable trading configuration
- an isolated run ID

The backtest integration must allow the campaign to provide a replay plan built
from the campaign-owned source.

Existing callers that do not provide an explicit replay plan must retain the
current automatic manifest-or-legacy behavior.

## 7. Deterministic execution plan

The execution plan must be generated fully before the first trial runs.

Plan ordering must be stable:

1. candidate generation order
2. walk-forward split order
3. train before validation
4. cost-scenario order

Every plan item must record:

- execution_index
- execution_id
- campaign_id
- trial_id
- split_name
- window_role
- cost_scenario_id
- start
- end_exclusive
- start_ts_ms
- end_ts_ms_exclusive
- inclusive_backtest_end_ts_ms
- run_id
- status
- artifact paths

The plan must validate:

- unique candidate IDs
- unique split names
- unique execution IDs
- unique run IDs
- aligned timeframe boundaries
- non-overlapping train and validation windows
- manifest-backed source ownership
- deterministic ordering

Replanning from the same effective specification, source fingerprint, and Git
commit must produce the same immutable execution plan.

## 8. Artifact layout

Canonical campaign root:

data/processed/research/scorer_campaigns/{campaign_id}/

Required immutable artifacts:

- campaign_manifest.json
- execution_plan.json

Required mutable or regenerated artifacts:

- campaign_status.json
- fold_results.csv
- candidate_results.csv
- rejections.csv
- failures.csv
- summary.json

Required trial artifact index:

trials/{execution_id}/result.json

Backtest decisions, trades, reports, and execution events may continue using
their existing processed namespaces. Their exact paths must be recorded in each
trial result and in the campaign indexes.

The campaign must not copy large decision or trade CSV files unnecessarily.

## 9. Artifact mutability

These artifacts must never be overwritten when non-empty:

- campaign_manifest.json
- execution_plan.json
- successful trials/{execution_id}/result.json

If an existing immutable artifact differs from newly generated canonical
content, the campaign must fail with an identity conflict.

These artifacts may be replaced atomically:

- campaign_status.json
- summary.json
- fold_results.csv
- candidate_results.csv
- rejections.csv
- failures.csv

All mutable JSON and aggregate CSV writes must use a temporary file followed by
os.replace().

## 10. Campaign status

Campaign status values:

- planned
- running
- completed
- completed_with_failures
- failed

Execution-item status values:

- pending
- running
- succeeded
- failed

Candidate disposition values:

- eligible
- rejected
- incomplete

campaign_status.json must include:

- campaign_id
- status
- created_at_utc
- started_at_utc
- updated_at_utc
- completed_at_utc
- planned_execution_count
- succeeded_execution_count
- failed_execution_count
- pending_execution_count
- eligible_candidate_count
- rejected_candidate_count
- incomplete_candidate_count
- last_execution_id

Operational timestamps must not affect deterministic campaign identity.

## 11. Resume semantics

Resume is allowed only when:

- campaign ID matches
- campaign manifest matches canonically
- execution plan matches canonically
- Git commit matches
- manifest fingerprint matches
- fixed strategy settings match
- cost assumptions match

Successful immutable execution results must be reused and not rerun.

A pending or failed execution may be attempted again.

Before retrying a failed or interrupted execution, the runner must ensure its
backtest output namespace is safe. It must never append to an ambiguous partial
result and treat it as a clean rerun.

A successful execution result is complete only when:

- the backtest returned successfully
- the expected decision path is recorded
- the expected trade path is recorded
- metrics were calculated
- the immutable trial result was written successfully

## 12. Trial failure semantics

One fold-run failure must be recorded without losing completed campaign
evidence.

failures.csv must record at least:

- campaign_id
- execution_id
- trial_id
- split_name
- window_role
- cost_scenario_id
- run_id
- failure_type
- failure_message
- failed_at_utc

Traceback details may be recorded in the immutable trial directory, but CSV
messages must be sanitized to one line.

A candidate with any required failed execution is incomplete and must not be
ranked as eligible.

The runner may continue after an isolated trial failure unless the failure
indicates a campaign-wide contract violation, including:

- source identity mismatch
- manifest audit failure
- campaign identity conflict
- fixed strategy contract mismatch
- execution-plan corruption
- artifact identity conflict

Campaign-wide contract violations terminate the campaign.

## 13. Metrics

Per fold and window, the campaign reuses TrialMetrics and records:

- trade_count
- winning_trades
- losing_trades
- breakeven_trades
- win_rate
- total_pnl_usd
- average_pnl_usd
- best_trade_pnl_usd
- worst_trade_pnl_usd
- maximum_drawdown_usd
- stop_hit_count
- stop_hit_rate
- time_stop_count
- long_trade_count
- short_trade_count
- first_exit_ts_ms
- last_exit_ts_ms

Any run that records a SHORT trade while SHORT is disabled is invalid.

Candidate aggregation must derive at least:

- total_train_trades
- total_validation_trades
- total_validation_pnl_usd
- worst_validation_fold_pnl_usd
- average_validation_pnl_usd
- maximum_validation_drawdown_usd
- positive_validation_fold_count
- negative_validation_fold_count
- validation_fold_count
- validation_return_to_drawdown
- validation_pnl_concentration

Division-by-zero behavior must be explicit and deterministic.

## 14. Minimum evidence and rejection rules

A candidate is rejected when any required condition fails.

Initial rejection reasons:

- execution_incomplete
- short_trade_detected
- minimum_total_trades_not_met
- minimum_validation_trades_per_split_not_met
- non_positive_total_validation_pnl
- non_positive_worst_validation_fold_pnl
- cost_stress_failure

The campaign manifest must record the exact enabled rejection rules and
threshold values.

A candidate with high profit but insufficient trade evidence remains rejected.

Rejected candidates and all rejection reasons must be preserved.

Rejection logic must not inspect the locked final out-of-sample window during
ordinary selection.

## 15. Cost sensitivity

Base execution uses the campaign's recorded fee and slippage assumptions.

Cost stress scenarios are explicit deterministic inputs. Each scenario records:

- cost_scenario_id
- fee_bps
- slippage_bps

Campaign identity must distinguish the base scenario from every stress scenario.

A candidate fails cost sensitivity when it violates the configured stress
acceptance policy.

No cost assumption may be inherited silently from the live paper namespace.

## 16. Ranking

Only eligible candidates may be ranked.

Ranking must be deterministic and use explicit ordered keys.

The initial ranking policy prioritizes:

1. worst validation-fold PnL
2. total validation PnL
3. validation return-to-drawdown
4. positive validation-fold count
5. total validation trade count
6. lower validation PnL concentration
7. stable trial ID as final tie-breaker

The exact ranking keys and directions must be recorded in the campaign
manifest.

Train metrics are supporting evidence. They must not override weak validation
performance.

## 17. Git identity

The campaign runner must resolve the current Git commit before execution.

The campaign must fail when:

- the commit cannot be resolved
- the working tree is dirty

The recorded Git identity must include:

- git_commit
- git_branch
- working_tree_clean

Remote push status is operational information and is not required for campaign
identity.

## 18. Fixed strategy protection

Campaign research must preserve strategy behavior that is outside the explicit
campaign search or research-override contract.

This includes live/default behavior not intentionally exposed as a research
control.

The campaign system must not silently change:

* LONG/SHORT policy
* Event-Risk connectivity
* stop semantics
* trailing semantics
* time-stop behavior
* cooldown semantics
* execution timing
* fee/slippage interpretation
* historical-gap policy
* live sizing behavior

Research-only sizing is an explicit exception to legacy backtest quantity
behavior only when research_order_notional_usd is supplied.

That override:

* is optional
* is disabled by default
* is recorded in campaign identity
* is passed through the research/backtest execution path
* does not modify files/strategy/rules.py live/default sizing behavior

Promotion of research sizing or any other research-only control into live
execution requires a separate explicit implementation and verification
decision.

## 19. Implementation boundaries

The smallest robust implementation should introduce:

- campaign specification and identity module
- campaign artifact and path helpers
- atomic JSON and CSV writing helpers
- deterministic execution-plan module
- campaign result aggregation and rejection module
- campaign CLI entry point
- optional explicit replay-plan support in run_backtest()
- explicit source-aware scorer trial execution

It should reuse:

- HistoricalResearchSource
- resolved walk-forward planning
- ScorerTrial generation and identity
- TrialRunRequest and scorer configuration
- TrialMetrics
- ReplayPlan and build_research_replay_plan()
- existing decisions, trades, and report writers
- existing research execution-event writer
- TradingConfig

It must not duplicate:

- historical auditing
- scorer construction
- backtest segment execution
- broker behavior
- metrics parsing

## 20. Verification contract

Campaign infrastructure changes require verification appropriate to the
changed contract.

Verification should cover, where applicable:

* deterministic campaign identity
* deterministic trial identity
* source and manifest identity
* half-open fold resolution
* physical-gap awareness
* isolated artifacts
* resume behavior
* identity-conflict failure
* partial-failure preservation
* aggregation
* rejection policy
* ranking policy
* Git identity
* protected final out-of-sample boundaries
* legacy/default behavior preservation

For research_order_notional_usd specifically, verification must prove:

1. the default None path preserves legacy/default serialization and behavior
2. an explicit positive value participates in campaign identity
3. old and new sizing campaigns cannot collide
4. the value reaches actual backtest execution
5. executed quantity produces the requested entry notional within expected
   numerical tolerance
6. live/default sizing remains unchanged

Data-dependent campaign verification belongs on OLD-BOX.

LOCAL static checks alone are not sufficient proof for historical execution
behavior.

## 21. Mission completion

The deterministic scorer campaign runner mission is complete as
infrastructure.

Implemented capabilities include:

* manifest_backed_v1 source enforcement
* one audited HistoricalResearchSource reused per campaign process
* deterministic scorer candidates
* deterministic campaign and execution identity
* half-open chronological folds
* isolated execution artifacts
* resume semantics
* failure preservation
* aggregation
* rejection policy
* ranking policy
* Git identity
* source-manifest identity
* realistic transaction-cost scenarios
* explicit research-only USD-notional sizing

Current versions:

* campaign schema version: 6
* trial-space version: scorer_parameter_space_v2_normalized_slope
* execution artifact contract: scorer_execution_artifacts_v2
* rejection policy: scorer_rejection_policy_v3
* ranking policy: scorer_ranking_policy_v1

Infrastructure completion does not imply that a profitable strategy has been
found.

Campaign outcomes remain research evidence and may validly reject every
candidate.

The active research mission and latest campaign results belong in HANDOFF.md
and milestone/research reports rather than in this contract.
