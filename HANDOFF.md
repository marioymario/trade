# HANDOFF — 2026-08-06 — SCORER CAMPAIGN DIAGNOSIS AND NEXT BEHAVIOR RESEARCH

--------------------------------------------------
1) CURRENT REPOSITORY IDENTITY
--------------------------------------------------

Branch:
main

Verified Git commit:
e44ccbafacd4029f389a6ca4ce729ada71436d76

GitHub:
https://github.com/marioymario/trade

Deployment state:
- pushed to origin/main
- deployed to OLD-BOX
- deployed working tree clean
- clean committed diagnostic run passed

--------------------------------------------------
2) RESEARCH DATASET
--------------------------------------------------

Data tag:
coinbase_history_2022_20260209

Symbol:
BTC/USD

Timeframe:
5m

Coverage:
2022-01-01 through 2026-02-09 exclusive

Manifest fingerprint:
43b10397ff6b513eb6917266e0cfccb4f866721ec829fff90b60fa907f10478c

Audited source facts:
- 1,500 daily Parquet partitions
- 431,842 stored bars
- 432,000 theoretical bars
- 158 missing bars
- seven confirmed source gaps
- eight physical replay segments
- no fabricated bars
- no cross-exchange price mixing
- independent warmup after each physical gap

--------------------------------------------------
3) ACTIVE STRATEGY POLICY
--------------------------------------------------

- LONG_ONLY
- SHORT remains quarantined
- Event-Risk remains disconnected
- paper-only
- no live strategy behavior was changed by the diagnostic work

--------------------------------------------------
4) WALK-FORWARD RESEARCH FOLDS
--------------------------------------------------

1. Train during 2022; validate first half of 2023.
2. Train through first half of 2023; validate second half of 2023.
3. Train through end of 2023; validate during 2024.

Fold boundaries remain frozen and chronological.

The locked later out-of-sample period has not been used for ordinary
candidate selection.

--------------------------------------------------
5) CAMPAIGN INFRASTRUCTURE STATUS
--------------------------------------------------

The deterministic multi-trial scorer campaign runner is complete.

Verified capabilities:
- manifest_backed_v1 enforcement
- one audited HistoricalResearchSource resolved per process
- deterministic candidate identities
- isolated execution artifacts
- resume behavior
- failure preservation
- aggregation and ranking
- rejection-policy enforcement
- Git and dataset identity recording
- realistic fee and slippage assumptions
- fold-level train and validation execution

Canonical command entry point:
files/research/run_scorer_campaign.py

--------------------------------------------------
6) COMPLETED CAMPAIGNS
--------------------------------------------------

Single-candidate campaign:
scorer_campaign_c6cb30445e28b95d

Result:
- 6 of 6 executions succeeded
- candidate rejected
- total validation PnL approximately -46.82 USD
- all three validation folds negative

Four-candidate campaign:
scorer_campaign_db7be3ff132cf415

Result:
- 24 of 24 executions succeeded
- all four candidates rejected

Best rejected candidate:
trial_efa354bc4327f1f6

Validation evidence:
- total validation PnL: +10.500562 USD
- worst validation fold: -9.281098 USD
- validation trades: 208
- positive folds: 2 of 3
- result strongly dependent on a small number of winners
- removing the best trade makes total validation PnL negative

Conclusion:
No scorer candidate is approved for deployment.

--------------------------------------------------
7) STOP-BEHAVIOR DIAGNOSTIC
--------------------------------------------------

Committed diagnostic:
- files/research/scorer_stop_diagnostic.py
- files/research/run_scorer_stop_diagnostic.py

Key evidence:
- 208 validation trades
- 188 stop exits
- 90.38 percent stop-exit rate
- 186 of 188 stopped trades first moved favorably
- weak trades commonly failed before meaningful progress
- evidence did not support trailing giveback as the primary defect

Interpretation:
The larger issue is weak entry continuation, not simply an overly tight
trailing stop.

--------------------------------------------------
8) ENTRY AND EARLY-PROGRESS DIAGNOSTIC
--------------------------------------------------

Committed diagnostic:
- files/research/scorer_entry_progress_diagnostic.py
- files/research/run_scorer_entry_progress_diagnostic.py

Diagnostic contract:
read_only_entry_early_progress_v2

Schema:
2

Verified clean-run identity:
e44ccbafacd4029f389a6ca4ce729ada71436d76

Verified results:
- trade count: 208
- reached 1R: 102
- did not reach 1R: 106
- scorer-confidence reconstruction difference: 0.0

Strict checkpoint availability:
- bar 1: 208
- bar 2: 192
- bar 3: 181
- bar 4: 165
- bar 6: 146

Anti-leakage guarantees:
- no future checkpoint bars
- exit-bar checkpoint features excluded
- outcome labels joined only after feature construction
- unavailable checkpoints not carried forward
- no strategy or backtest replay inside the diagnostic
- threshold output explicitly marked diagnostic-only

RVOL guarantees:
- physical-segment scoped
- current bar excluded from prior-volume mean
- no confirmed-gap crossing

Canonical artifact root:
data/processed/research/scorer_campaigns/
scorer_campaign_db7be3ff132cf415/
diagnostics/entry_early_progress/
trial_efa354bc4327f1f6/

Artifacts:
- diagnostic_summary.json
- entry_early_progress_trades.csv
- feature_group_summary.csv
- fold_summary.csv
- threshold_analysis.csv
- winner_concentration.json

--------------------------------------------------
9) NOTEBOOK EXPLORATION
--------------------------------------------------

Notebook name:
scorer_early_failure_policy_exploration_v1.ipynb

The notebook reconstructed the completed trade cost model exactly:
- 13 basis points against round-trip notional

It then evaluated static checkpoint-close replacement PnL.

Important result:
Very low bar-3 MFE identified a group of rapidly failing trades.

Useful exploratory region:
- checkpoint near bar 3
- MFE below roughly 0.05R to 0.10R

A bounded two-feature search found higher static estimates using secondary
conditions such as:
- scorer confidence
- confidence change
- one-bar return
- EMA slow slope
- close ratio

However:
- thousands of combinations were inspected
- most improvement came from the 2024 fold
- one validation fold remained negative
- H2 2023 was often unchanged
- results are static counterfactual estimates
- no full-engine replay has yet validated the policy
- exact notebook thresholds are not approved parameters

--------------------------------------------------
10) CURRENT RESEARCH CONCLUSION
--------------------------------------------------

Observed:
Low early MFE contains useful information about weak continuation.

Exploratory:
A simple secondary condition may protect delayed winners while still
exiting some weak trades early.

Not proven:
- full-engine profitability improvement
- fold robustness
- neighboring-parameter stability under replay
- drawdown improvement
- generalization to untouched out-of-sample data
- production suitability

No strategy behavior was changed.

--------------------------------------------------
11) BEST NEXT MISSION
--------------------------------------------------

Build the smallest robust engine-level early-failure behavior contract.

Candidate configuration interface:
- early_failure_enabled: bool
- early_failure_checkpoint_bars: int
- early_failure_mfe_threshold_r: float
- optional secondary-condition field only if justified by engine replay

Required implementation rules:
- disabled by default
- explicit serialized research identity
- no hidden behavior-changing defaults
- preserve current live and legacy behavior
- baseline equivalence when disabled
- use existing engine and broker interfaces
- no notebook-only execution semantics

Required verification:
1. inspect actual strategy, broker, and backtest exit interfaces
2. implement the disabled-by-default contract
3. prove exact baseline equivalence
4. replay a small bounded policy set through the full engine
5. compare fold PnL, drawdown, trade evidence, costs, and winner sacrifice
6. reject exact thresholds that are not stable across neighboring values
7. only then expose surviving behavior controls to campaign search

--------------------------------------------------
12) LONGER-TERM RESEARCH DIRECTION
--------------------------------------------------

After one behavior contract is engine-verified, expand campaign search
beyond scorer-only values.

Future controllable categories may include:
- scorer thresholds and scales
- entry filters
- initial-stop behavior
- trailing activation and distance
- time-stop duration
- cooldown
- early-failure exits
- volatility and volume controls
- categorical market-regime permissions
- conditional parameters

Search should be staged:
1. broad bounded search
2. stable-region refinement
3. limited interaction search
4. frozen candidate comparison
5. untouched final out-of-sample confirmation

Do not run an uncontrolled Cartesian explosion across every parameter.

--------------------------------------------------
13) NON-NEGOTIABLES
--------------------------------------------------

- SHORT stays quarantined.
- Event-Risk stays isolated.
- Research remains paper-only.
- Missing bars are never fabricated.
- Known gaps are never silently crossed.
- Manifest-backed campaigns never silently fall back to legacy replay.
- LOCAL is not used for data-dependent execution.
- Full research execution happens on OLD-BOX.
- Static notebook counterfactuals are not treated as engine proof.
- Validation folds are not changed after viewing results.
- Generated artifacts and rejected candidates remain reproducible.
- No real-money execution without robust out-of-sample evidence.

--------------------------------------------------
14) WORKING CONTRACT
--------------------------------------------------

- inspect actual code before editing
- use the smallest robust architecture
- edit on LOCAL
- deploy to OLD-BOX
- run dependency and data-aware verification on OLD-BOX
- commit and push only after proof
- rerun from the clean committed revision
- update notes after the clean run
- keep current documents current-only
- archive superseded handoffs

--------------------------------------------------
15) CURRENT LABEL
--------------------------------------------------

Scorer campaign infrastructure:
COMPLETE

Initial scorer campaigns:
COMPLETE — ALL CANDIDATES REJECTED

Stop-behavior diagnosis:
COMPLETE

Read-only entry-progress diagnosis:
COMPLETE AND CLEAN-RUN VERIFIED

Early-failure behavior:
EXPLORATORY — NOT ENGINE-VALIDATED

Best next mission:
ENGINE-LEVEL EARLY-FAILURE CONTRACT AND FULL REPLAY
