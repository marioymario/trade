TRADING RESEARCH PAUSE / CONTINUATION HANDOFF

Date: 2026-08-21
Branch: research/data-universe-expansion
Authoritative milestone commit:
f72637f

Status:
SAFE PAUSE POINT

Purpose:
Preserve the exact research state, evidence, workflow, unresolved questions,
and next missions so the project can be resumed later without reconstructing
months of context.


==============================================================================
1. PRIMARY PROJECT OBJECTIVE
==============================================================================

Build a robust trading system with repeatable out-of-sample net profitability
under realistic costs and controlled risk.

Priority order:

1. Out-of-sample profitability.
2. Cross-period consistency.
3. Cross-asset consistency.
4. Drawdown control.

The objective is not to maximize historical backtest P&L.

The objective is to identify a strategy architecture whose edge is broad,
repeatable, economically meaningful, and capable of surviving realistic
execution friction.


==============================================================================
2. CURRENT AUTHORITATIVE CODE STATE
==============================================================================

Git repository:

    https://github.com/marioymario/trade

Active research branch:

    research/data-universe-expansion

Current authoritative research milestone commit:

    f72637f
    Close adaptive range ATR research milestone

LOCAL research worktree:

    /home/gto5080/Projects/trade-entry-quality

OLD-BOX research runtime:

    /home/kk7wus/Projects/trade-entry-quality

LOCAL is used for:

    - editing
    - static checks
    - Git operations

OLD-BOX is used for:

    - dependency-aware validation
    - historical-data execution
    - backtests
    - research campaigns
    - artifact verification

Git is NOT used on OLD-BOX.

Research changes should continue to follow:

    edit LOCAL
    -> static check LOCAL
    -> deploy
    -> verify/run OLD-BOX
    -> commit/push LOCAL only after successful OLD-BOX verification


==============================================================================
3. LIVE / PRODUCTION SAFETY STATE
==============================================================================

Live strategy behavior remains unchanged.

LONG-only baseline remains intact.

SHORT remains quarantined.

Event-Risk remains disconnected from the live/main strategy.

Research is paper/backtest only.

The adaptive range + ATR research work has NOT been promoted to live capital.

No production approval exists.


==============================================================================
4. FROZEN COINBASE USD RESEARCH UNIVERSE V1
==============================================================================

Universe ID:

    research_universe_coinbase_usd_v1

Universe fingerprint:

    f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a

PRIMARY research assets:

    BTC/USD
    ETH/USD
    SOL/USD
    ADA/USD
    XLM/USD
    LINK/USD
    DOGE/USD
    LTC/USD

Historical data is:

    - manifest-backed
    - audited
    - gap-aware
    - physical-segment scoped

No synthetic bars are permitted.

No interpolation is permitted.

No cross-exchange substitution is permitted.

No replay across physical gaps is permitted.


==============================================================================
5. DEVELOPMENT HISTORY NOW CONSUMED
==============================================================================

The following periods are development-visible and may no longer be treated as
unseen evidence:

    2023-H1
    2023-H2
    2024
    2025

The final historical reserve was:

    2026-01-01T00:00:00Z
    through
    2026-02-09T00:00:00Z

That reserve has now been consumed exactly once.

Therefore:

    2026-01-01 through 2026-02-09 is permanently unavailable
    for future candidate selection, tuning, repair, or confirmation.

Future independent validation must use genuinely new future data.


==============================================================================
6. RANGE-FACTOR DISCOVERY
==============================================================================

Important structural feature:

    current_range_vs_prior_10_mean

Definition:

    current candle range
    divided by
    mean range of prior 10 bars

The current candle is excluded from the prior mean.

The calculation is segment/gap scoped.

Useful range gate:

    current_range_vs_prior_10_mean >= 1.25

Range filtering repeatedly improved strategy behavior.

An adaptive chronological range policy was developed:

    Use RANGE for a new period only when RANGE beat BASELINE
    in the immediately preceding OOS period.

This range component remains supported as useful research structure.


==============================================================================
7. 2025 ADAPTIVE RANGE CONFIRMATION
==============================================================================

Frozen 2025 adaptive range candidate:

    baseline P&L:
        -68.061361

    adaptive candidate P&L:
        -28.119034

    improvement:
        +39.942327

The candidate materially improved the baseline but remained negative.

Formal result:

    FAIL

This result was preserved.

The range factor therefore remained a useful component, but was insufficient
as a complete profitable strategy.


==============================================================================
8. 2025 FAILURE DIAGNOSIS
==============================================================================

2025 adaptive candidate:

    trades:
        1695

    P&L:
        -28.119034

Exit decomposition:

    stop_hit:
        1569 trades
        -351.553157 P&L

    time_stop:
        126 trades
        +323.434123 P&L

A large population of stop-hit losers had very little favorable development.

Approximately:

    933 stop trades
    pre-exit MFE < 1%
    only 2 winners
    approximately -892.214349 P&L

MFE is future information.

It was used only as a diagnostic label and must never be used directly as an
entry rule.


==============================================================================
9. ATR / VOLATILITY DISCOVERY
==============================================================================

Signal-time ATR emerged as the strongest broad discriminator of productive
versus low-development trades.

Feature:

    signal_atr_pct

Pooled AUC:

    approximately 0.5932

Direction:

    higher ATR -> more productive trade behavior

Directional consistency:

    8 / 8 assets

2025 half-year consistency:

    H1 approximately 0.6044
    H2 approximately 0.5701

The productive-trade rate increased almost monotonically across ATR quintiles.

This led to a simple abstention hypothesis:

    Do not enter when signal-time volatility is too low for the
    strategy's payoff geometry.


==============================================================================
10. PREDECLARED ATR DEVELOPMENT EXPERIMENT
==============================================================================

Experiment:

    adaptive_range_atr_development_v1

Policies:

    adaptive_range_control
    ATR >= 0.005
    ATR >= 0.006
    ATR >= 0.007

The ATR gate was universal across all active entries.

Development periods:

    2023-H1
    2023-H2
    2024
    2025

Assets:

    8 PRIMARY assets

Total executions:

    128


Overall results:

CONTROL

    total P&L:
        +252.821390

    positive periods:
        2 / 4

    worst period:
        -28.119034

    trades:
        4824


ATR >= 0.005

    total P&L:
        +381.579326

    delta:
        +128.757936

    positive periods:
        4 / 4

    worst period:
        +7.118723

    trades:
        3967

    asset-periods not worse than control:
        26 / 32


ATR >= 0.006

    total P&L:
        +338.185175

    positive periods:
        4 / 4

    weaker cross-period and cross-asset breadth


ATR >= 0.007

    total P&L:
        +397.383516

    positive periods:
        4 / 4

    highest pooled P&L

    but:
        only 18 / 32 asset-periods not worse
        greater concentration
        more aggressive trade suppression


==============================================================================
11. WHY ATR >= 0.005 WAS SELECTED
==============================================================================

ATR >= 0.005 was selected as the leading V2 candidate because robustness was
prioritized over maximum pooled P&L.

ATR >= 0.005:

    improved control in 4 / 4 periods

    produced positive P&L in 4 / 4 periods

    improved all 8 assets in aggregate

    produced 26 / 32 asset-periods not worse than control

    retained materially more trades than ATR >= 0.007

Aggregate asset deltas for ATR >= 0.005:

    BTC:
        +8.315698

    ETH:
        +5.009838

    SOL:
        +32.432913

    ADA:
        +3.059464

    XLM:
        +0.248077

    LINK:
        +35.090537

    DOGE:
        +28.477871

    LTC:
        +16.123538

Do NOT resume by searching finer ATR thresholds.

Do NOT optimize around 0.005.

The current evidence must remain intact.


==============================================================================
12. FINAL ROBUSTNESS BATTERY
==============================================================================

Experiment:

    adaptive_range_atr_robustness_v1

Candidate:

    adaptive_range_atr_ge_0_005

Base structural robustness:

    PASS

Candidate trades:

    3967

Candidate median asset-period maximum drawdown:

    13.324454

Control median asset-period maximum drawdown:

    17.004570

Asset-periods with >25% drawdown deterioration:

    2

Leave-one-asset-out:

    PASS in every case

Leave-one-period-out:

    PASS in every case

Asset positive-delta concentration:

    approximately 0.2725

Period positive-delta concentration:

    approximately 0.4001


Cost stresses:

1.5x base:

    fee:
        12 bps

    slippage:
        7.5 bps

    candidate:
        -135.050319

    control:
        -375.279475

    candidate delta:
        +240.229156

    candidate positive periods:
        2 / 4


2.0x base:

    fee:
        16 bps

    slippage:
        10 bps

    candidate:
        -651.679964

    control:
        -1003.380340

    candidate delta:
        +351.700376

    candidate positive periods:
        0 / 4


Formal robustness result:

    FAIL

Reason:

    absolute profitability did not survive the high-cost stress gates.

Important:

The ATR candidate beat control in every stressed period.

Therefore:

    structural robustness:
        PASS

    relative cost robustness:
        PASS

    absolute high-cost profitability:
        FAIL


==============================================================================
13. EMPIRICAL CHALLENGER DECISION
==============================================================================

The formal robustness FAIL was preserved.

However, because structural robustness passed and the ATR effect continued to
improve the strategy under higher transaction costs, the candidate was frozen
as:

    FROZEN EMPIRICAL CHALLENGER

This did NOT mean:

    production approval
    robustness PASS
    mechanism proven
    live-capital approval

It allowed one terminal unseen-reserve falsification test.


==============================================================================
14. 2026 ADAPTIVE RANGE MAP
==============================================================================

The chronological rule required the 2026 range roles to be derived from 2025
range-vs-baseline outcomes.

The old confirmation artifact lacked counterfactual RANGE executions for:

    ETH/USD
    DOGE/USD
    LTC/USD

Those three 2025-only counterfactuals were executed.

Results:

ETH:

    baseline:
        +10.853450

    range:
        +13.463958

    delta:
        +2.610508

    2026 role:
        RANGE


DOGE:

    baseline:
        -41.584064

    range:
        -28.083248

    delta:
        +13.500816

    2026 role:
        RANGE


LTC:

    baseline:
        +31.096198

    range:
        +29.757113

    delta:
        -1.339086

    2026 role:
        BASELINE


Final frozen 2026 map:

RANGE:

    BTC
    ETH
    SOL
    ADA
    XLM
    LINK
    DOGE

BASELINE:

    LTC


==============================================================================
15. TERMINAL 2026 RESERVE RESULT
==============================================================================

Experiment:

    adaptive_range_atr_2026_reserve_v1

Reserve:

    2026-01-01
    through
    2026-02-09

Control:

    P&L:
        -45.759313

    trades:
        137

    median maximum drawdown:
        6.779714


Frozen ATR >= 0.005 challenger:

    P&L:
        -36.420502

    trades:
        115

    median maximum drawdown:
        5.736845


Improvement:

    +9.338811 P&L

Approximate loss reduction:

    20.4%

Asset breadth:

    6 / 8 assets beat control

    7 / 8 assets were not worse

    1 / 8 candidate assets was positive


Terminal interpretation:

    RELATIVE_EFFECT_GENERALIZED_BUT_ABSOLUTE_ECONOMICS_INSUFFICIENT


==============================================================================
16. FINAL RANGE + ATR CONCLUSION
==============================================================================

The strongest defensible conclusion is:

    RANGE / VOLATILITY ABSTENTION APPEARS TO CAPTURE A REAL,
    REPEATABLE MARKET-STATE PHENOMENON.

However:

    THE CURRENT COMPLETE STRATEGY DOES NOT YET SHOW SUFFICIENT,
    RELIABLE ABSOLUTE ECONOMIC EDGE ACROSS ALL REGIMES.

The phenomenon generalized.

The complete trading edge did not.

Therefore:

    useful empirical component:
        YES

    production-ready strategy:
        NO


==============================================================================
17. IMPORTANT RESEARCH PROHIBITIONS
==============================================================================

Do NOT use 2026 outcomes to:

    tune ATR

    tune range threshold

    remove ETH

    favor ADA

    change asset-specific parameters

    redesign exits based on individual 2026 trades

    choose a new scorer using 2026 labels

    repair the frozen challenger

The 2026 reserve is consumed permanently.

Future independent validation must come from new future data.


==============================================================================
18. NEXT PRIMARY MISSION: EVENT-RISK RESEARCH
==============================================================================

Event-Risk is the next leading research direction.

Reason:

Range and ATR describe market motion and local opportunity geometry.

Event-Risk may provide a genuinely different information axis:

    geopolitical risk
    conflict escalation
    macro/political shocks
    unusually important public statements
    rapid shifts in external uncertainty

The core question is NOT:

    Does news move Bitcoin?

The core research question is:

    Does point-in-time Event-Risk identify a different population
    of bad trades that range + ATR >= 0.005 cannot identify?


Initial Event-Risk mission should be:

1. Audit the current Event-Risk implementation.

2. Confirm exactly what is connected versus disconnected.

3. Audit historical data availability.

4. Prove historical Event-Risk states are reproducible point-in-time.

5. Verify timestamps and publication/as-of semantics.

6. Identify coverage gaps.

7. Prevent future-information leakage.

8. Keep Event-Risk disconnected from production.

9. Use the existing range + ATR >= 0.005 architecture as the research control.

10. Start with a very small hypothesis:

        adaptive range + ATR >= 0.005
        versus
        adaptive range + ATR >= 0.005
        + abstain from entries during predefined elevated Event-Risk states

11. Determine whether Event-Risk rejects trades that ATR does NOT already reject.

12. Evaluate across 2023-2025 only.

13. Do not use the consumed 2026 reserve for Event-Risk development.


==============================================================================
19. EVENT-RISK OBSERVATIONAL HYPOTHESIS
==============================================================================

A research hypothesis worth testing is that high-impact geopolitical or
political communication may alter short-term crypto market behavior.

Examples may include:

    war / peace statements
    escalation / de-escalation language
    major policy announcements
    high-impact statements from political leaders
    abrupt changes in geopolitical expectations

This should NOT be encoded as:

    positive words -> buy
    negative words -> sell

The potentially useful information may instead be:

    uncertainty regime
    surprise
    conflict escalation
    de-escalation
    abnormal information flow
    elevated event-risk state

This is an empirical hypothesis only.

It must be tested against point-in-time historical evidence before being
connected to the trading system.


==============================================================================
20. FUTURE RESEARCH RADAR: STOCHASTIC / PROBABILISTIC MODELS
==============================================================================

Keep stochastic and probabilistic modeling on the research radar.

Do NOT replace or delete the deterministic architecture.

The deterministic system remains valuable because it provides:

    reproducibility
    interpretable rules
    stable research contracts
    clean controls
    auditable failure modes

Potential future probabilistic extensions may include:

    probabilistic regime classification

    Hidden Markov Models

    Bayesian state estimation

    state-space models

    probabilistic entry-quality models

    calibrated probability of favorable excursion

    uncertainty-aware abstention

    probabilistic volatility / return distributions

    Monte Carlo / bootstrap robustness analysis

    probabilistic capital allocation

    ensemble models

The key potential advantage is not that stochastic models are universally
better than deterministic models.

Their value may be that they can represent:

    uncertainty
    regime probability
    confidence
    distributions
    transition behavior

A future architecture should preferably allow deterministic and probabilistic
models to coexist so each can be evaluated against the same research and
execution contracts.


==============================================================================
21. OTHER IMPORTANT FUTURE RESEARCH QUESTIONS
==============================================================================

Potential future research after Event-Risk:

    opportunity-to-cost gating

    portfolio-level abstention

    cross-sectional opportunity ranking

    stronger entry-quality discrimination

    probabilistic regime models

    stochastic models

    execution-cost optimization

    maker/taker execution realism

    spread/fill modeling

    forward paper validation on genuinely unseen future data

Do not pursue all of these simultaneously.

Prefer one clean hypothesis at a time.


==============================================================================
22. PROJECT WORKFLOW RULES TO PRESERVE
==============================================================================

For code/architecture changes:

    inspect actual interfaces first

    agree on the plan

    make the smallest robust change

    edit LOCAL

    run lightweight/static checks LOCAL

    deploy to OLD-BOX

    run dependency/data-aware validation OLD-BOX

    commit/push only after OLD-BOX verification


Do not make opportunistic unrelated changes.

Do not change defaults without agreement.

Do not redesign architecture during implementation without stopping and
reconsidering the plan.

Preserve working legacy paths unless a replacement is explicitly verified and
retired.

For long OLD-BOX runs:

    use nohup or equivalent detached execution

so LOCAL can be shut down safely.


Terminal rules:

    use python3

    do not use set -euo pipefail

    clearly label LOCAL versus OLD-BOX

    commands should be provided one step at a time


==============================================================================
23. RELEVANT CURRENT RESEARCH FILES
==============================================================================

Primary closed milestone documentation:

    docs/research/adaptive_range_atr_research_checkpoint_2026-08-18.md

Frozen challenger contract:

    files/research/contracts/
    adaptive_range_atr_empirical_challenger_v1.json

Development runner:

    files/research/run_adaptive_range_atr_development.py

Robustness runner:

    files/research/run_adaptive_range_atr_robustness.py

2025 counterfactual completion:

    files/research/run_2025_range_counterfactual_completion.py

Terminal 2026 reserve runner:

    files/research/run_adaptive_range_atr_2026_reserve.py


==============================================================================
24. RELEVANT OLD-BOX RESULT ARTIFACTS
==============================================================================

Development:

    data/processed/research/experiments/
    adaptive_range_atr_development_v1/result.json

Robustness:

    data/processed/research/experiments/
    adaptive_range_atr_robustness_v1/result.json

2025 counterfactual completion:

    data/processed/research/experiments/
    range_factor_2025_counterfactual_completion_v1/result.json

2026 terminal reserve:

    data/processed/research/reserves/
    adaptive_range_atr_2026_reserve_v1/result.json


==============================================================================
25. EXACT RESUME POINT
==============================================================================

When returning to the project:

DO NOT resume by changing ATR or range parameters.

DO NOT rerun the 2026 reserve as a new validation experiment.

DO NOT connect Event-Risk directly to live trading.

The next action is:

    EVENT-RISK ARCHITECTURE AND HISTORICAL-PROVENANCE AUDIT

Start by inspecting the existing Event-Risk implementation and documenting:

    current modules
    state definitions
    source inputs
    as-of semantics
    historical-storage availability
    historical replay capability
    gaps
    leakage risks
    integration points
    currently disconnected interfaces

Then create an Event-Risk research plan BEFORE implementation.

The first experiment should test whether Event-Risk provides incremental
information beyond the already-discovered range + ATR phenomenon.


==============================================================================
26. SAFE PAUSE STATUS
==============================================================================

Current research branch:

    research/data-universe-expansion

Authoritative milestone commit:

    f72637f

Git status at milestone close:

    clean

Remote branch:

    up to date

Range + ATR research chapter:

    CLOSED

2026 reserve:

    CONSUMED

Production/live strategy:

    UNCHANGED

Event-Risk:

    NEXT PRIMARY RESEARCH MISSION
    DISCONNECTED FROM PRODUCTION

Stochastic/probabilistic models:

    FUTURE RESEARCH RADAR
    NO ARCHITECTURE CHANGE YET


This is a safe point to pause the project.

The project can be resumed from this document without reconstructing the
range + ATR research history from scratch.
