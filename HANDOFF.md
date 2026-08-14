# HANDOFF — 2026-08-13 — MULTI-ASSET BASELINE AND USD-NORMALIZED RESEARCH

--------------------------------------------------
1) CURRENT PHASE
--------------------------------------------------

Historical-data preparation:
COMPLETE

Coinbase USD Research Universe V1:
COMPLETE AND FROZEN

Research Eligibility Policy V1:
IMPLEMENTED AND VERIFIED

Current mission:
Establish a comparable multi-asset strategy/scorer baseline across the
PRIMARY_COMPARABLE population using:

- one frozen scorer candidate
- frozen chronological walk-forward folds
- manifest-backed historical sources
- realistic fees and slippage
- equal USD order notional

No broad strategy/scorer optimization should begin until this corrected
baseline is complete and its evidence has been audited.

--------------------------------------------------
2) CURRENT REPOSITORY IDENTITY
--------------------------------------------------

Research branch:
research/data-universe-expansion

Current verified Git commit:
6a534b9521addedb668874370f095417be3683f1

Commit purpose:
Add USD-normalized research sizing.

GitHub:
https://github.com/marioymario/trade

Deployment state:
- pushed to origin/research/data-universe-expansion
- deployed to OLD-BOX research staging
- deployed Git identity clean
- dependency/data-aware OLD-BOX verification passed
- execution-level USD-sizing smoke test passed

LOCAL research worktree:
/home/gto5080/Projects/trade-entry-quality

OLD-BOX research staging:
/home/kk7wus/Projects/trade-entry-quality

OLD-BOX canonical runtime:
/home/kk7wus/Projects/trade

LOCAL remains for:
- editing
- Git
- lightweight static checks

OLD-BOX remains authoritative for:
- historical data
- pandas/data-dependent validation
- backtests
- research campaigns
- practical runtime verification

--------------------------------------------------
3) LIVE / PRODUCTION SAFETY POLICY
--------------------------------------------------

- LONG_ONLY baseline remains unchanged.
- SHORT remains quarantined.
- Event-Risk remains disconnected.
- Research remains paper-only.
- No research sizing behavior was added to the live sizing function.
- Existing sizing behavior remains active when no research sizing override
  is supplied.

Research-layer changes must not casually modify live strategy behavior.

--------------------------------------------------
4) COINBASE USD RESEARCH UNIVERSE V1
--------------------------------------------------

Universe ID:
research_universe_coinbase_usd_v1

Universe fingerprint:
f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a

Status:
FROZEN

Membership:
29 Coinbase USD spot markets

Final verification:
- 29/29 members verified
- all deployed manifest hashes match the frozen contract
- all canonical raw datasets exist
- 27 newly acquired and audited datasets
- 2 reused canonical datasets
- 0 failures

V1 membership is immutable.

A material membership or contract change requires a new universe version.

Historical data quality is intentionally explicit and heterogeneous.

Representative missing 5-minute bar counts:

BTC:
158

ETH:
447

SOL:
181

ADA:
199

BICO:
221716

OXT:
178654

TRAC:
171550

COTI:
122413

DASH:
105026

Sparse markets are not repaired by fabricating candles.

--------------------------------------------------
5) PRIMARY COMPARABLE RESEARCH POPULATION
--------------------------------------------------

PRIMARY_COMPARABLE:

BTC/USD
ETH/USD
SOL/USD
ADA/USD
XLM/USD
LINK/USD
DOGE/USD
LTC/USD

Secondary research population:

DOT/USD
BCH/USD
SHIB/USD
ATOM/USD

The current baseline concerns PRIMARY_COMPARABLE only.

--------------------------------------------------
6) PRIMARY-8 CANONICAL HISTORICAL SOURCES
--------------------------------------------------

BTC/USD

Data tag:
coinbase_history_2022_20260209

Manifest fingerprint:
43b10397ff6b513eb6917266e0cfccb4f866721ec829fff90b60fa907f10478c


ETH/USD

Data tag:
coinbase_eth_history_2018_20260209

Manifest fingerprint:
f870466613827e1b7a7062d9428956444f7e48e159394a9aeaf7a5b7349f8314


SOL/USD

Data tag:
coinbase_sol_history_2022_20260209

Manifest fingerprint:
64c0383b71c6b9b2194b8e1d6d524533cfbb499fad16f4e301e12088b850c56b


ADA/USD

Data tag:
coinbase_ada_history_2022_20260209

Manifest fingerprint:
aff2a5960dcc59bc537058f18aa93c0a78137888142af51886fe5f02078d784b


XLM/USD

Data tag:
coinbase_xlm_history_2022_20260209

Manifest fingerprint:
b02663efe32c75b756048b1c57e1b922cb128a7d7a4473aff98d53fa876b1781


LINK/USD

Data tag:
coinbase_link_history_2022_20260209

Manifest fingerprint:
8e99eab7fe69ee3d975e871513f7ebabd78c7a3ada053d6f3cfce2750ecb8fbc


DOGE/USD

Data tag:
coinbase_doge_history_2022_20260209

Manifest fingerprint:
6376e83b0b5d7ed2cba3d0a32311ac3f706b222302cf918c6e02062485eb0063


LTC/USD

Data tag:
coinbase_ltc_history_2022_20260209

Manifest fingerprint:
00828a1a0c6f563363376e1b8aae548c877c67156e1149fd05614e049234efc8

--------------------------------------------------
7) WALK-FORWARD CONTRACT
--------------------------------------------------

Frozen chronological folds:

1.

Train:
2022

Validate:
2023-H1


2.

Train:
2022 through 2023-H1

Validate:
2023-H2


3.

Train:
2022 through 2023

Validate:
2024


Ranges are half-open.

Fold definitions remain frozen after viewing results.

The 2025+ period remains protected out-of-sample data.

It must not be inspected during ordinary strategy/scorer development or
candidate selection.

--------------------------------------------------
8) CURRENT SCORER CONTRACT
--------------------------------------------------

Research scorer contract:
entry_scorer_v3_normalized_slope

Frozen baseline candidate:
trial_096291cf0738ff2f

The same scorer candidate is used across every PRIMARY symbol.

The purpose of this baseline is not to prove that this candidate is
optimal.

The purpose is to determine how one fixed strategy/scorer configuration
behaves across:

- multiple chronological periods
- multiple assets
- identical cost assumptions
- comparable economic exposure

--------------------------------------------------
9) FIRST PRIMARY-8 BASELINE
--------------------------------------------------

The first PRIMARY-8 campaign completed successfully.

Execution result:
- 8 assets
- 3 walk-forward folds per asset
- train + validation execution per fold
- 48/48 executions succeeded
- zero execution failures

However, the backtest inherited the existing strategy sizing rule:

size_position(...) = 0.01 base-asset units

This meant:

BTC used 0.01 BTC per trade.
ETH used 0.01 ETH per trade.
SOL used 0.01 SOL per trade.
XLM used 0.01 XLM per trade.
etc.

Therefore raw USD PnL from that campaign is NOT economically comparable
across assets.

Example historical BTC entry:

Entry price:
41961.11 USD

Quantity:
0.01 BTC

Entry notional:
419.6111 USD

A 0.01-unit trade in a low-priced asset may represent only cents of
exposure.

The first campaign is NOT discarded.

Still-valid evidence from the fixed-base-quantity run includes:
- trade chronology
- trade counts
- entry and exit events
- stop and exit frequencies
- signal behavior
- outcome geometry that does not depend on monetary weighting

Do not compare raw dollar PnL from that run across assets.

Do not treat its fold PnL signs as sizing-independent evidence.

The equal-USD-notional rerun proved that changing economic weighting can
change aggregate fold PnL and even fold sign without changing the underlying
entry/exit chronology.

BTC is the clearest example:

Fixed 0.01-BTC baseline:
- total validation PnL approximately -0.70 USD
- positive validation folds: 1/3

Equal-100-USD-notional baseline:
- total validation PnL +3.351793603110794 USD
- positive validation folds: 3/3

Therefore the first run remains useful for behavioral diagnosis, but
capital-dependent fold metrics must be taken from the normalized campaign.

--------------------------------------------------
10) RESEARCH-ONLY USD NORMALIZATION
--------------------------------------------------

A research-only order-notional contract is now implemented.

Interface:

research_order_notional_usd: float | None

Behavior:

When None:
existing legacy sizing behavior is preserved.

When supplied:
research entry quantity is calculated from the requested USD notional.

Current PRIMARY baseline:

research_order_notional_usd = 100.0

The override is explicitly passed through:

CampaignSpecification
-> campaign execution
-> TrialRunRequest
-> run_backtest
-> SegmentExecutionRequest

The live sizing function was not modified.

--------------------------------------------------
11) CAMPAIGN IDENTITY GUARANTEE
--------------------------------------------------

research_order_notional_usd participates in serialized campaign identity
only when it is explicitly supplied.

This is intentional.

A default/legacy campaign with:

research_order_notional_usd = None

does NOT serialize the new field.

Therefore historical campaign identities remain stable.

A campaign using explicit USD-normalized research sizing receives a new
immutable campaign identity.

OLD-BOX verification:

legacy research_order_notional_usd:
None

legacy serialized key present:
False

Result:
PASS

All eight USD-normalized PRIMARY campaigns received unique campaign IDs.

Collision count with the original fixed-quantity PRIMARY campaigns:
0

--------------------------------------------------
12) EXECUTION-LEVEL USD-SIZING VERIFICATION
--------------------------------------------------

A real historical BTC trade was replayed through the new research sizing
path before commit.

Historical entry:

2022-01-08T21:45:00Z

Entry price:

41961.11 USD

Old quantity:

0.01 BTC

Old entry notional:

419.6111 USD

USD-normalized quantity:

0.0023831590727700007 BTC

Target entry notional:

100.0 USD

Observed entry notional:

100.0 USD

Result:

USD-NOTIONAL EXECUTION: PASS

This practical dependency/data-aware verification occurred on OLD-BOX
before the change was committed.

--------------------------------------------------
13) AUTHORITATIVE $100 PRIMARY-8 BASELINE
--------------------------------------------------

Git commit:

6a534b9521addedb668874370f095417be3683f1

Baseline contract:

multi_asset_baseline_v1_usd_notional

Research order notional:

100.0 USD

Scorer contract:

entry_scorer_v3_normalized_slope

Frozen trial:

trial_096291cf0738ff2f


Authoritative campaign IDs:

BTC/USD
scorer_campaign_917be2805ed4291c

ETH/USD
scorer_campaign_4a6289bf4a3a40d2

SOL/USD
scorer_campaign_fd7c9bf6432dddcd

ADA/USD
scorer_campaign_04f5e571dbd17277

XLM/USD
scorer_campaign_434f2f1f7d09b02a

LINK/USD
scorer_campaign_1f60581971274d77

DOGE/USD
scorer_campaign_4408b47b25418119

LTC/USD
scorer_campaign_b97380baf68537a5


Authoritative manifest audit:

PASS

Verified across all eight campaigns:
- correct clean Git commit
- correct research branch
- working_tree_clean = true
- research_order_notional_usd = 100.0
- scorer-v3
- frozen trial
- canonical source manifest
- six planned executions per symbol

--------------------------------------------------
14) CURRENT RUN STATUS
--------------------------------------------------

The authoritative $100 PRIMARY-8 baseline was launched detached on
OLD-BOX using nohup.

Log:

ops/logs/multi_asset_baseline_v1_usd100_20260813.log

PID file:

ops/logs/multi_asset_baseline_v1_usd100_20260813.pid

Final status:

COMPLETE AND AUDITED

Execution result:

- 8/8 campaigns completed
- 48/48 planned backtests completed
- 0 failure rows
- all campaign artifacts present
- authoritative clean Git identity preserved

The corrected equal-notional baseline is now complete.

BTC/USD is the only PRIMARY_COMPARABLE member that satisfies the current
candidate rejection policy.

BTC validation result:

- total validation PnL: +3.351793603110794 USD
- worst validation fold PnL: +0.6354935014137432 USD
- positive validation folds: 3/3
- validation trades: 123
- validation return-to-drawdown: 0.5420428901185574
- validation PnL concentration: 0.45481933852137013
- disposition: eligible
- rejection reasons: none

The remaining seven PRIMARY members are rejected.

ETH/USD:
- total validation PnL: +23.304964566758713 USD
- worst fold: -5.082660314983147 USD
- positive folds: 2/3
- trades: 167
- rejection: non_positive_worst_validation_fold_pnl

SOL/USD:
- total validation PnL: -14.566887121013814 USD
- worst fold: -44.82398608984841 USD
- positive folds: 2/3
- trades: 744
- rejections:
  non_positive_total_validation_pnl
  non_positive_worst_validation_fold_pnl

ADA/USD:
- total validation PnL: +42.36691710205077 USD
- worst fold: -11.586296263873146 USD
- positive folds: 2/3
- trades: 500
- rejection: non_positive_worst_validation_fold_pnl

XLM/USD:
- total validation PnL: +182.20320145322626 USD
- worst fold: -3.6091956518482835 USD
- positive folds: 2/3
- trades: 371
- rejection: non_positive_worst_validation_fold_pnl

LINK/USD:
- total validation PnL: +4.896114557733826 USD
- worst fold: -20.063629504431322 USD
- positive folds: 1/3
- trades: 524
- rejection: non_positive_worst_validation_fold_pnl

DOGE/USD:
- total validation PnL: -29.932821902252368 USD
- worst fold: -31.506710301079426 USD
- positive folds: 1/3
- trades: 675
- rejections:
  non_positive_total_validation_pnl
  non_positive_worst_validation_fold_pnl

LTC/USD:
- total validation PnL: +42.44136919371948 USD
- worst fold: -12.589653694453151 USD
- positive folds: 2/3
- trades: 324
- rejection: non_positive_worst_validation_fold_pnl

Important interpretation:

Eligibility is not deployment approval.

BTC passed the current minimum campaign rejection policy, but its aggregate
profit and return-to-drawdown are modest.

The principal positive BTC evidence is chronological consistency:
all three validation folds are positive.

The broader strategy/scorer configuration is not cross-asset robust:
seven of eight PRIMARY members fail at least one current rejection rule.

--------------------------------------------------
15) RESULTS INTERPRETATION POLICY
--------------------------------------------------

Primary research objective:

Find robust combinations of strategy/scorer parameters that produce
repeatable out-of-sample profitability under realistic costs and
controlled risk.

Priority order:

1. out-of-sample profitability
2. cross-period consistency
3. cross-asset consistency
4. drawdown control

Important evidence includes:
- worst validation fold PnL
- total validation PnL
- positive validation fold count
- validation return-to-drawdown
- validation trade count
- PnL concentration
- rejection reasons
- cross-asset consistency
- behavior under realistic transaction costs

Do not promote a candidate because of:
- one unusually profitable asset
- one unusually profitable fold
- one large winning trade
- high trade count alone
- high aggregate PnL hiding weak folds

Robustness matters more than isolated maximum profit.

--------------------------------------------------
16) IMMEDIATE NEXT STEP
--------------------------------------------------

The authoritative $100 PRIMARY-8 baseline is complete and audited.

The next research mission should use the normalized cross-asset contrast
rather than immediately launching broad optimization.

Recommended next mission:

CROSS-ASSET DISCRIMINATION DIAGNOSIS

Primary question:

Why does the same frozen strategy/scorer configuration produce 3/3 positive
validation folds on BTC while the other seven PRIMARY members fail one or
more validation periods?

The diagnosis should compare BTC against rejected assets using existing
entry-time, market-state, volatility, continuation, stop/exit, and outcome
evidence under the same chronological and economic-exposure contract.

The purpose is to identify whether the separation is driven primarily by:

- entry-quality discrimination
- volatility structure
- trend persistence
- scorer saturation or scaling
- stop/exit interaction
- market-regime mismatch
- another reproducible structural difference

Do not optimize BTC parameters yet.

First determine which structural properties distinguish the sole survivor
from the rejected population.

This diagnosis is not a separate research detour.

Its deliverable should be a reduced and defensible common parameter space
for the next multi-asset search.

Planned progression:

1. use BTC-led discrimination to identify useful features, directions,
   interactions, and plausible parameter ranges
2. eliminate weak, redundant, saturated, or unjustifiably broad dimensions
3. run common parameter candidates across the full PRIMARY_COMPARABLE
   population using the frozen equal-USD-notional contract
4. search for broad cross-asset robustness regions rather than a single
   maximum-PnL candidate
5. only after a common robust region is identified, investigate whether one
   or a very small number of normalized asset/regime adjustment controls can
   improve transfer
6. use constrained per-asset optimization only as a later diagnostic of how
   far each market wants to move away from the shared solution

The objective remains a transferable strategy/scorer structure, not eight
independent asset-specific recipes.

--------------------------------------------------
17) NEXT RESEARCH DECISION
--------------------------------------------------

Do not assume the next research direction before the corrected baseline
is complete.

Possible future directions include:

- entry-quality discrimination
- scorer structure
- stop/exit behavior
- regime conditioning
- volatility controls
- strategy/scorer interactions

The baseline evidence should determine which hypothesis has the strongest
justification.

Do not begin an uncontrolled broad parameter search merely because the
campaign machinery exists.

--------------------------------------------------
18) CAMPAIGN INFRASTRUCTURE STATUS
--------------------------------------------------

The deterministic scorer campaign infrastructure is operational.

Current capabilities include:
- manifest_backed_v1 source enforcement
- deterministic campaign and candidate identities
- explicit scorer contracts
- isolated execution artifacts
- resume behavior
- failure preservation
- aggregation
- rejection policy
- ranking policy
- Git identity recording
- source-manifest identity
- realistic fee/slippage scenarios
- chronological walk-forward execution
- explicit research USD-notional sizing

Current campaign schema version:
6

Current research trial-space version:
scorer_parameter_space_v2_normalized_slope

Current execution artifact contract:
scorer_execution_artifacts_v2

Current rejection policy:
scorer_rejection_policy_v3

Current ranking policy:
scorer_ranking_policy_v1

--------------------------------------------------
19) RESEARCH WORKFLOW
--------------------------------------------------

Preferred engineering workflow:

ADJUST
-> DEPLOY DIRTY
-> CHECK OLD-BOX
-> FIX / REPEAT
-> COMMIT / PUSH
-> CLEAN DEPLOY
-> AUTHORITATIVE OLD-BOX VERIFY

LOCAL:
editing, Git, lightweight static checks

OLD-BOX:
historical data, pandas-dependent verification, backtests, research
campaigns, runtime proof

Do not commit behavior-changing research work before practical OLD-BOX
verification.

When several reproducible experiments share the same setup, prefer a
single reusable batch pipeline instead of unnecessary symbol-by-symbol
manual work.

--------------------------------------------------
20) NON-NEGOTIABLES
--------------------------------------------------

- SHORT stays quarantined.
- Event-Risk stays disconnected unless explicitly activated in a future
  controlled research phase.
- Research remains paper-only.
- Missing historical bars are never fabricated.
- Known physical gaps are never silently crossed.
- Manifest-backed campaigns never silently fall back to legacy replay.
- LOCAL is not used for historical/data-dependent execution.
- Runtime verification happens on OLD-BOX.
- Live sizing behavior is not changed by research sizing.
- Historical campaign identities remain reproducible.
- Validation folds remain frozen.
- 2025+ protected OOS remains untouched during ordinary development.
- Static diagnostics are not treated as engine proof.
- Rejected candidates remain reproducible.
- No real-money deployment without robust out-of-sample evidence.

--------------------------------------------------
21) CURRENT LABEL
--------------------------------------------------

Historical-data preparation:
COMPLETE

Coinbase USD Research Universe V1:
COMPLETE AND FROZEN

Research Eligibility Policy V1:
COMPLETE AND VERIFIED

PRIMARY comparable population:
FROZEN FOR CURRENT RESEARCH

Scorer-v3 baseline candidate:
FROZEN

Legacy fixed-quantity PRIMARY-8 baseline:
COMPLETE — DIAGNOSTICALLY USEFUL, NOT CROSS-ASSET USD-COMPARABLE

Research USD-notional sizing:
IMPLEMENTED, OLD-BOX VERIFIED, COMMITTED, AND CLEANLY DEPLOYED

Authoritative $100 PRIMARY-8 baseline:
COMPLETE AND AUDITED — BTC ELIGIBLE, 7/8 REJECTED

Protected 2025+ OOS:
UNTOUCHED

Best next action:
CROSS-ASSET DISCRIMINATION DIAGNOSIS BEFORE FURTHER PARAMETER OPTIMIZATION
