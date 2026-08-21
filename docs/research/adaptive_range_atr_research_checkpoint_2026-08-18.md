# Adaptive Range + ATR Research Checkpoint

Date: 2026-08-18
Status: CLOSED RESEARCH MILESTONE
Research branch: research/data-universe-expansion
Experiment: adaptive_range_atr_development_v1

This document records the research state immediately after the adaptive-range
plus universal ATR abstention experiment and before the final robustness
battery.

Its purpose is to preserve the chronology, hypotheses, evidence, failures,
and candidate-selection reasoning before any further validation is performed.

This is not a final strategy approval and is not authorization for live
capital deployment.


==============================================================================
1. RESEARCH OBJECTIVE
==============================================================================

The project objective remains:

Develop a trading system that demonstrates repeatable out-of-sample net
profitability under realistic costs and controlled risk.

Priority order:

1. Out-of-sample profitability.
2. Cross-period consistency.
3. Cross-asset consistency.
4. Drawdown control.

The research process does not optimize solely for maximum historical profit.
A candidate with lower aggregate profit may be preferred when its evidence is
broader and more stable across assets and periods.


==============================================================================
2. DATA AND ANTI-LEAKAGE STATE
==============================================================================

Research universe:

    research_universe_coinbase_usd_v1

Universe fingerprint:

    f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a

Primary comparable research assets:

    BTC/USD
    ETH/USD
    SOL/USD
    ADA/USD
    XLM/USD
    LINK/USD
    DOGE/USD
    LTC/USD

Historical replay remains manifest-backed and gap-aware.

No synthetic bars, interpolation, cross-exchange substitution, or replay
across physical data gaps is permitted.

Development-visible periods now include:

    2023-H1
    2023-H2
    2024
    2025

The 2025 period was originally held for confirmation. It has now been consumed
and therefore is development-visible.

The final reserve remains:

    2026-01-01T00:00:00Z
    through
    2026-02-09T00:00:00Z

The 2026 reserve has NOT been consumed.

It must remain sealed until one V2 candidate is frozen following the planned
robustness battery.


==============================================================================
3. RANGE-FACTOR DISCOVERY
==============================================================================

The structural feature:

    current_range_vs_prior_10_mean

measures the current candle range divided by the mean range of the prior
10 bars.

The current candle is excluded from the historical mean and the calculation
is physical-segment scoped.

A threshold of:

    current_range_vs_prior_10_mean >= 1.25

showed useful economic discrimination.

Earlier development comparison:

    baseline validation P&L:       +254.064651
    universal range gate P&L:      +271.594176
    improvement:                    +17.529525

An adaptive range policy was then developed.

The rule was chronological:

    First validation period:
        use BASELINE.

    Each later validation period:
        use RANGE >= 1.25 only when the immediately preceding
        out-of-sample period showed positive range-minus-baseline P&L.

This produced the following historical adaptive schedule.

2023-H1:

    BASELINE:
        BTC ETH SOL ADA XLM LINK DOGE LTC

2023-H2:

    RANGE:
        BTC ADA XLM LINK DOGE

    BASELINE:
        ETH SOL LTC

2024:

    RANGE:
        BTC SOL ADA XLM LINK DOGE

    BASELINE:
        ETH LTC

2025:

    RANGE:
        BTC SOL ADA XLM LINK

    BASELINE:
        ETH DOGE LTC

The mechanically reconstructed 2025 selection exactly matched the previously
frozen confirmation contract, providing an explicit check that 2025 outcomes
were not used to construct the 2025 asset map.


==============================================================================
4. 2025 CONFIRMATION RESULT
==============================================================================

The adaptive-range candidate entered 2025 as a frozen confirmation policy.

Results:

    baseline P&L:             -68.061361
    adaptive candidate P&L:   -28.119034
    improvement:              +39.942327
    relative improvement:     approximately 58.69%

The candidate materially improved the baseline but remained negative.

Therefore the formal confirmation result was:

    FAIL

The strategy was not promoted.

Important interpretation:

The range factor remained useful because it substantially reduced losses and
improved the selected assets, but it was insufficient as a standalone solution.

The failure was retained as evidence rather than repaired by retuning against
the confirmation period.


==============================================================================
5. 2025 FAILURE DIAGNOSIS
==============================================================================

The 2025 adaptive candidate produced:

    trades:       1695
    total P&L:    -28.119034

Exit-reason decomposition:

    stop_hit:
        trades:   1569
        P&L:      -351.553157

    time_stop:
        trades:   126
        P&L:      +323.434123

Within stop-hit trades:

    winners:
        440 trades
        P&L: +622.352111
        median pre-exit MFE: approximately 2.472%
        median holding time: 13 bars

    losers:
        1129 trades
        P&L: -973.905267
        median pre-exit MFE: approximately 0.497%
        median holding time: 5 bars

A particularly important diagnostic group was:

    stop-hit trades with pre-exit MFE < 1%:
        approximately 933 trades
        only 2 winners
        approximately -892.214349 P&L

This indicated that a major problem was not simply how profitable trades were
being exited.

A large population of trades showed very little favorable development after
entry.

MFE is future information.

Therefore:

    MFE is a diagnostic label only.

It must never be used directly as an entry rule.


==============================================================================
6. POINT-IN-TIME FEATURE DIAGNOSIS
==============================================================================

Trade entries were joined to the immediately preceding 5-minute decision:

    signal_ts_ms = entry_ts_ms - 300000

The investigation compared information available at signal time against the
future low-development diagnostic label.

Among the strongest broad signals was:

    signal_atr_pct

Pooled discrimination:

    AUC approximately 0.5932
    direction: HIGHER ATR associated with productive trades

Cross-asset directional consistency:

    8 / 8 assets

2025 half-year consistency:

    H1 AUC approximately 0.6044
    H2 AUC approximately 0.5701

Per-asset ATR AUC:

    BTC     0.6327
    ETH     0.5493
    SOL     0.6042
    ADA     0.5481
    XLM     0.6341
    LINK    0.6317
    DOGE    0.5637
    LTC     0.6053

initial_stop_pct showed essentially the same discrimination because the
initial stop distance is derived from ATR.

The evidence therefore pointed toward signal-time volatility as the underlying
factor rather than a new independent stop-distance factor.


==============================================================================
7. ATR ECONOMIC SHAPE
==============================================================================

2025 pooled ATR quintiles showed an almost monotonic relationship between
signal-time volatility and productive-trade rate.

Approximate results:

Q1:

    ATR range:        0.002926 - 0.004792
    trades:           341
    productive rate:  0.349
    P&L:              -32.138215

Q2:

    ATR range:        0.004793 - 0.005621
    trades:           338
    productive rate:  0.396
    P&L:              -15.248447

Q3:

    ATR range:        0.005623 - 0.006667
    trades:           338
    productive rate:  0.432
    P&L:              -34.332109

Q4:

    ATR range:        0.006675 - 0.008281
    trades:           339
    productive rate:  0.481
    P&L:              -20.185552

Q5:

    ATR range:        0.008284 - 0.085744
    trades:           339
    productive rate:  0.590
    P&L:              +73.785290

This supported a simple hypothesis:

    The strategy should abstain from entering when signal-time volatility
    is too low for its payoff geometry.

The exact best-looking 2025 threshold was deliberately NOT adopted.

Instead, a small predeclared family of round thresholds was chosen to avoid
fitting the candidate to 2025.


==============================================================================
8. PREDECLARED ADAPTIVE RANGE + ATR EXPERIMENT
==============================================================================

Experiment ID:

    adaptive_range_atr_development_v1

Runner:

    files/research/run_adaptive_range_atr_development.py

Control:

    Existing chronological adaptive-range policy.

Candidate family:

    adaptive_range_atr_ge_0_005
    adaptive_range_atr_ge_0_006
    adaptive_range_atr_ge_0_007

The ATR condition was applied universally to every active entry.

This included assets whose adaptive-range role for a period was BASELINE.

Therefore the test was:

    existing adaptive-range behavior
    PLUS
    universal signal_atr_pct abstention

and not a replacement for the adaptive range policy.

Evaluation periods:

    2023-H1
    2023-H2
    2024
    2025

Assets:

    8

Policies:

    4

Total executions:

    4 periods x 8 assets x 4 policies = 128 executions

The experiment used the existing scorer, execution costs, position sizing,
stops, exits, LONG-only policy, and disconnected Event-Risk state.

No shared production strategy behavior was intentionally changed.


==============================================================================
9. EXPERIMENT EXECUTION AND RETRY HARDENING
==============================================================================

The first full execution attempt exposed a stale-artifact collision involving
deterministic run IDs and research execution-event files.

The new experiment runner initially attempted to use the existing partial
backtest cleanup helper.

That did not fully remove the stale artifacts because canonical processed paths
normalize tags through safe_tag(), while the cleanup call used mixed-case
deterministic run IDs.

The fix was isolated to the new runner.

Before each deterministic execution, the runner now applies safe_tag() to the
data tag and run ID before invoking the existing partial-backtest cleanup
helper.

No shared campaign helper was modified.

The exact previously failing BTC / 2023-H1 / ATR >= 0.006 execution was rerun
against stale artifacts and succeeded.

After removing only the partial experiment wrapper directory, the complete
experiment was relaunched detached on OLD-BOX.

Final execution result:

    128 / 128 executions completed
    result.json produced
    reserved_2026_outcomes_consumed = false


==============================================================================
10. OVERALL DEVELOPMENT RESULTS
==============================================================================

ADAPTIVE RANGE CONTROL

    total P&L:                     +252.821390
    delta vs control:                +0.000000
    positive periods:                2 / 4
    worst-period P&L:               -28.119034
    total trades:                    4824
    asset-periods not worse:         32 / 32


ATR >= 0.005

    total P&L:                     +381.579326
    delta vs control:             +128.757936
    positive periods:                4 / 4
    worst-period P&L:                +7.118723
    total trades:                    3967
    asset-periods not worse:         26 / 32


ATR >= 0.006

    total P&L:                     +338.185175
    delta vs control:              +85.363785
    positive periods:                4 / 4
    worst-period P&L:               +15.368046
    total trades:                    3096
    asset-periods not worse:         16 / 32


ATR >= 0.007

    total P&L:                     +397.383516
    delta vs control:             +144.562126
    positive periods:                4 / 4
    worst-period P&L:               +37.642469
    total trades:                    2260
    asset-periods not worse:         18 / 32


==============================================================================
11. PERIOD ROBUSTNESS
==============================================================================

2023-H1

    control:
        P&L:             -27.188644
        trades:          666
        positive assets: 3 / 8
        median DD:       17.789729

    ATR >= 0.005:
        P&L:              +7.118723
        delta:           +34.307367
        trades:           541
        positive assets:  4 / 8
        median DD:        11.152549

    ATR >= 0.006:
        P&L:             +15.368046
        delta:           +42.556690

    ATR >= 0.007:
        P&L:             +37.642469
        delta:           +64.831113


2023-H2

    control:
        P&L:             +62.698129

    ATR >= 0.005:
        P&L:             +71.239271
        delta:            +8.541143

    ATR >= 0.006:
        P&L:             +48.843977
        delta:           -13.854152

    ATR >= 0.007:
        P&L:             +68.504698
        delta:            +5.806569


2024

    control:
        P&L:            +245.430940

    ATR >= 0.005:
        P&L:            +279.827104
        delta:           +34.396165

    ATR >= 0.006:
        P&L:            +227.647324
        delta:           -17.783616

    ATR >= 0.007:
        P&L:            +241.167895
        delta:            -4.263045


2025

    control:
        P&L:             -28.119034
        trades:           1695
        positive assets:  4 / 8
        median DD:        27.995672

    ATR >= 0.005:
        P&L:             +23.394228
        delta:           +51.513261
        trades:           1380
        positive assets:  6 / 8
        median DD:        20.292141

    ATR >= 0.006:
        P&L:             +46.325829
        delta:           +74.444862

    ATR >= 0.007:
        P&L:             +50.068454
        delta:           +78.187488


==============================================================================
12. WHY ATR >= 0.005 CURRENTLY LEADS
==============================================================================

ATR >= 0.007 produced the highest aggregate development P&L.

It is therefore important to record explicitly why ATR >= 0.005 is currently
preferred instead.

ATR >= 0.005 improved the adaptive-range control in:

    4 / 4 development periods

ATR >= 0.007 improved the control in:

    3 / 4 development periods

ATR >= 0.005 produced:

    26 / 32 asset-periods not worse than control

ATR >= 0.007 produced:

    18 / 32 asset-periods not worse than control

ATR >= 0.005 also retained substantially more trades:

    3967

versus:

    2260

for ATR >= 0.007.

The selection objective is robustness, not the highest pooled P&L.


==============================================================================
13. CROSS-ASSET EVIDENCE FOR ATR >= 0.005
==============================================================================

Total delta versus adaptive-range control by asset:

    BTC/USD:     +8.315698
    ETH/USD:     +5.009838
    SOL/USD:    +32.432913
    ADA/USD:     +3.059464
    XLM/USD:     +0.248077
    LINK/USD:   +35.090537
    DOGE/USD:   +28.477871
    LTC/USD:    +16.123538

Therefore:

    8 / 8 assets improved in aggregate.

Period improvement counts:

    BTC:     3 / 4
    ETH:     3 / 4
    SOL:     4 / 4
    ADA:     3 / 4
    XLM:     2 / 4
    LINK:    4 / 4
    DOGE:    3 / 4
    LTC:     4 / 4

No asset has a negative total delta under ATR >= 0.005.

XLM is the weakest improvement case and is effectively flat in aggregate
relative to control.

This breadth is materially stronger than ATR >= 0.007.


==============================================================================
14. CONTRAST WITH ATR >= 0.007
==============================================================================

ATR >= 0.007 remains important evidence.

Its success supports the existence of a genuine volatility-related mechanism
rather than a single isolated threshold result.

However its asset behavior is substantially more concentrated.

Total delta versus control:

    BTC/USD:    -12.579208
    ETH/USD:     -6.609451
    SOL/USD:    +76.202306
    ADA/USD:     +2.677820
    XLM/USD:     -8.447193
    LINK/USD:   +58.135687
    DOGE/USD:   +47.484914
    LTC/USD:    -12.302750

Four assets are worse in aggregate than control.

BTC is worse in:

    4 / 4 periods

The aggregate advantage of ATR >= 0.007 is therefore more dependent on a
smaller group of strong contributors, particularly SOL, LINK, and DOGE.

This is not sufficient reason to reject ATR >= 0.007 as a useful research
result.

It is sufficient reason not to prefer it merely because it has the highest
pooled P&L.


==============================================================================
15. CURRENT RESEARCH CONCLUSION
==============================================================================

The leading V2 development candidate is:

    adaptive range policy
    PLUS
    universal signal_atr_pct >= 0.005

Candidate shorthand:

    ATR >= 0.005

This is a provisional candidate selection.

It is NOT yet a frozen final candidate.

It has earned advancement because it currently has the strongest combination
of:

    - positive P&L in 4 / 4 development periods
    - improvement over control in 4 / 4 periods
    - positive aggregate delta on 8 / 8 assets
    - 26 / 32 asset-periods not worse than control
    - improved behavior in previously weak periods
    - meaningful drawdown improvement
    - substantial remaining trade count
    - less contribution concentration than ATR >= 0.007


==============================================================================
16. RESEARCH DISCIPLINE DECISION
==============================================================================

Do NOT search additional ATR thresholds at this stage.

In particular, do not refine around:

    0.005
    0.006
    0.007

based on the development results already observed.

Doing so would convert the current evidence into increasingly tuned
development-history optimization.

ATR >= 0.007 should remain documented as a strong neighboring configuration
and supporting evidence for the volatility hypothesis.

ATR >= 0.006 remains part of the experiment record but is not currently a
leading candidate because it underperformed control in both 2023-H2 and 2024.


==============================================================================
17. NEXT MISSION — FINAL DEVELOPMENT ROBUSTNESS BATTERY
==============================================================================

Run a final robustness battery on ONE candidate only:

    adaptive_range_atr_ge_0_005

Compare it against:

    adaptive_range_control

Required checks:

1. Cost stress.

2. Drawdown comparison.

3. Trade-count sufficiency.

4. Leave-one-asset-out portfolio robustness.

5. Leave-one-period-out robustness.

6. Contribution concentration.

7. Verify that no single asset carries the overall result.

8. Verify that no single period carries the overall result.

9. Verify that the candidate remains materially better under reasonable
   perturbations that do not constitute a new parameter search.

10. Confirm again that no 2026 outcomes were consumed.


==============================================================================
18. FREEZE GATE
==============================================================================

If ATR >= 0.005 survives the final robustness battery:

    Freeze exactly one V2 candidate contract.

The frozen contract must record at minimum:

    - research-universe identity
    - historical-manifest identities
    - adaptive range policy
    - range threshold
    - ATR threshold
    - scorer/config identity
    - cost assumptions
    - execution assumptions
    - LONG-only state
    - Event-Risk disconnected state
    - development periods consumed
    - final reserve boundary
    - relevant code/Git identity
    - candidate-selection rationale

Only after this contract is frozen should the final 2026 reserve be opened.


==============================================================================
19. FINAL RESERVE RULE
==============================================================================

The remaining protected interval is:

    2026-01-01T00:00:00Z
    through
    2026-02-09T00:00:00Z

This interval must not be used:

    - to choose ATR thresholds
    - to choose assets
    - to modify adaptive range roles
    - to redesign the scorer
    - to modify stops or exits
    - to select cost assumptions
    - to repair a failed robustness result

Once the V2 candidate is frozen, the 2026 reserve should be consumed once as
the final unseen historical test.

A failed final reserve result must be recorded as a failure.

It must not be repaired by tuning against the same reserve period.


==============================================================================
20. CURRENT STATUS
==============================================================================

As of this checkpoint:

    Coinbase USD Universe V1:               FROZEN
    Research Eligibility Policy V1:         VERIFIED
    Adaptive range factor:                  VALIDATED COMPONENT
    2025 adaptive confirmation:             FAILED FORMAL PROMOTION
    2025 failure diagnosis:                 COMPLETE
    Signal-time ATR hypothesis:             SUPPORTED
    ATR development experiment:             COMPLETE, 128/128
    Leading V2 candidate:                   ATR >= 0.005
    Final robustness battery:               NEXT
    V2 candidate contract:                  NOT YET FROZEN
    2026 reserve:                           SEALED / UNCONSUMED
    Live strategy behavior:                 UNCHANGED
    SHORT policy:                           QUARANTINED
    Event-Risk integration:                 DISCONNECTED

This checkpoint intentionally stops before the final robustness battery so the
candidate-selection reasoning is preserved before seeing that evidence.


==============================================================================
21. FINAL ROBUSTNESS BATTERY RESULT
==============================================================================

Experiment:

    adaptive_range_atr_robustness_v1

Candidate tested:

    adaptive_range_atr_ge_0_005

Control:

    adaptive_range_control

The robustness battery was executed across the same four development periods
and eight PRIMARY assets.

Base-cost structural robustness results:

    total candidate trades:
        3967

    candidate median asset-period maximum drawdown:
        13.324454

    control median asset-period maximum drawdown:
        17.004570

    asset-periods with >25% drawdown deterioration:
        2

    leave-one-asset-out:
        candidate remained positive in every case
        candidate beat control in every case

    leave-one-period-out:
        candidate remained positive in every case
        candidate beat control in every case

    asset positive-delta concentration:
        approximately 0.2725

    period positive-delta concentration:
        approximately 0.4001

Therefore the candidate passed the structural robustness checks.


Cost-stress scenarios were newly introduced for this robustness battery:

    stress_1_5x:
        fee_bps:       12.0
        slippage_bps:   7.5

    stress_2_0x:
        fee_bps:       16.0
        slippage_bps:  10.0


Stress 1.5x:

    candidate total P&L:
        -135.050319

    control total P&L:
        -375.279475

    candidate delta versus control:
        +240.229156

    positive candidate periods:
        2 / 4


Stress 2.0x:

    candidate total P&L:
        -651.679964

    control total P&L:
        -1003.380340

    candidate delta versus control:
        +351.700376

    positive candidate periods:
        0 / 4


The candidate improved upon control in every individual stressed period.

However absolute profitability did not survive the predeclared high-cost
stress requirements.

Therefore the formal robustness experiment result is:

    FAIL

This FAIL must remain part of the permanent research record.


==============================================================================
22. INTERPRETATION OF THE ROBUSTNESS FAILURE
==============================================================================

The candidate did NOT fail due to:

    - insufficient trade count
    - excessive median drawdown
    - severe broad drawdown deterioration
    - dependence on a single asset
    - dependence on a single period
    - loss of advantage relative to control under higher costs

Those checks passed.

The candidate failed because absolute profitability became negative under the
newly introduced 1.5x and 2.0x transaction-cost assumptions.

At the same time, the candidate's advantage over control increased as costs
rose.

This supports the interpretation that ATR >= 0.005 is rejecting trades with
poor economic quality and reducing exposure to trading friction.

It does NOT demonstrate that the strategy is insensitive to transaction costs.

The base-cost phenomenon and the high-cost failure are both retained as true
observations.


==============================================================================
23. EMPIRICAL CHALLENGER DECISION
==============================================================================

The research process originally stated that the candidate would enter the
final 2026 reserve only if it passed the complete robustness battery.

That condition was not met.

The robustness decision remains:

    FAIL

However, all structural robustness checks passed and the candidate continued
to dominate the control under every stressed period despite losing absolute
profitability.

The 1.5x and 2.0x cost-stress thresholds were also first introduced during
this robustness phase and are not an established historical production
promotion standard for the project.

For those reasons, the project makes an explicit research-policy amendment
BEFORE inspecting any 2026 outcome.

The candidate is now classified as:

    FROZEN EMPIRICAL CHALLENGER

This classification does NOT:

    - convert the robustness FAIL into PASS
    - approve live trading
    - prove the underlying mechanism
    - prove transaction-cost robustness
    - permit further parameter tuning

Its purpose is to allow one final unseen falsification test of the empirical
phenomenon.


==============================================================================
24. FROZEN EMPIRICAL CHALLENGER
==============================================================================

The challenger is frozen as:

    adaptive chronological range policy
    PLUS
    universal signal_atr_pct >= 0.005

Range threshold:

    current_range_vs_prior_10_mean >= 1.25

ATR threshold:

    signal_atr_pct >= 0.005

No additional ATR threshold search is permitted before the final reserve test.

No asset-specific ATR thresholds are permitted.

No modification of the adaptive range schedule is permitted.

No scorer redesign is permitted.

No stop or exit redesign is permitted.

No asset removal based on observed development performance is permitted.

No change to LONG-only policy is permitted.

Event-Risk remains disconnected.

The same research execution assumptions, position notional, fee/slippage base
assumptions, scorer identity, historical source contracts, and PRIMARY asset
universe must be used.


==============================================================================
25. PURPOSE OF THE FINAL 2026 TEST
==============================================================================

The final reserve test is NOT intended to prove that the candidate is safe for
production.

It is a falsification test of the following empirical hypothesis:

    Adaptive range selection plus universal ATR >= 0.005 represents a
    persistent market-state effect that improves this strategy's economics
    outside the development data used to discover it.

The remaining protected interval is:

    2026-01-01T00:00:00Z
    through
    2026-02-09T00:00:00Z

This interval has not yet been consumed.

The challenger must be evaluated exactly once against this interval.

Possible interpretations:

1. Candidate profitable and broadly better than control:

       Strong evidence that the empirical phenomenon generalized to unseen
       data.

2. Candidate negative but materially better than control:

       Evidence that the phenomenon may generalize, but the economic edge is
       insufficient for reliable profitability.

3. Candidate loses its relative advantage or deteriorates materially:

       Evidence against the hypothesis and against promotion of the current
       challenger.

Whichever result occurs must be accepted without repairing the challenger
against the 2026 reserve.


==============================================================================
26. STATUS BEFORE OPENING THE FINAL RESERVE
==============================================================================

Robustness experiment:                    COMPLETE
Formal robustness decision:              FAIL
Structural robustness:                   PASS
Relative cost robustness:                PASS
Absolute high-cost profitability:        FAIL
Leading ATR threshold:                   0.005
Candidate classification:                FROZEN EMPIRICAL CHALLENGER
Further development tuning:              PROHIBITED before reserve test
2026 reserve:                            SEALED / UNCONSUMED
Live strategy behavior:                  UNCHANGED
SHORT policy:                            QUARANTINED
Event-Risk integration:                  DISCONNECTED

The next permitted research action is preparation of the frozen challenger
contract followed by one terminal unseen-reserve test.


==============================================================================
27. TERMINAL 2026 UNSEEN-RESERVE RESULT
==============================================================================

Experiment:

    adaptive_range_atr_2026_reserve_v1

Frozen challenger:

    adaptive range policy
    PLUS
    universal signal_atr_pct >= 0.005

Reserve window:

    2026-01-01T00:00:00Z
    through
    2026-02-09T00:00:00Z

The reserve was consumed exactly once after the challenger, adaptive 2026
asset-policy map, costs, scorer, strategy behavior, and evaluation rules had
been frozen.

Reserve status:

    consumed:                true
    consumption count:       1

The reserve is permanently unavailable for future candidate selection,
parameter tuning, strategy repair, or confirmation.


==============================================================================
28. 2026 AGGREGATE RESULT
==============================================================================

Adaptive-range control:

    total P&L:               -45.759313
    total trades:             137
    median maximum drawdown:   6.779714

Frozen ATR >= 0.005 challenger:

    total P&L:               -36.420502
    total trades:             115
    median maximum drawdown:   5.736845

Candidate improvement versus control:

    P&L delta:                +9.338811
    approximate loss reduction:
                              20.4%

Trade-count reduction:

    22 fewer trades
    approximately 16.1% fewer trades

Asset breadth:

    assets beating control:       6 / 8
    assets not worse than control:7 / 8
    candidate-positive assets:    1 / 8

The terminal reserve interpretation produced by the frozen runner was:

    RELATIVE_EFFECT_GENERALIZED_BUT_ABSOLUTE_ECONOMICS_INSUFFICIENT


==============================================================================
29. 2026 ASSET RESULTS
==============================================================================

BTC/USD

    adaptive role:           RANGE
    control P&L:             -3.945322
    candidate P&L:           -3.945322
    delta:                   +0.000000

ETH/USD

    adaptive role:           RANGE
    control P&L:             -4.359707
    candidate P&L:           -5.185690
    delta:                   -0.825984

SOL/USD

    adaptive role:           RANGE
    control P&L:            -10.609524
    candidate P&L:           -7.822011
    delta:                   +2.787513

ADA/USD

    adaptive role:           RANGE
    control P&L:             -1.682618
    candidate P&L:           +1.261630
    delta:                   +2.944248

XLM/USD

    adaptive role:           RANGE
    control P&L:             -6.542272
    candidate P&L:           -6.056409
    delta:                   +0.485863

LINK/USD

    adaptive role:           RANGE
    control P&L:             -7.969472
    candidate P&L:           -5.780720
    delta:                   +2.188752

DOGE/USD

    adaptive role:           RANGE
    control P&L:             -4.691484
    candidate P&L:           -4.320746
    delta:                   +0.370739

LTC/USD

    adaptive role:           BASELINE
    control P&L:             -5.958913
    candidate P&L:           -4.571233
    delta:                   +1.387680


==============================================================================
30. FINAL INTERPRETATION OF THE RANGE + ATR MISSION
==============================================================================

The terminal unseen reserve did NOT establish reliable absolute profitability.

The challenger therefore remains unsuitable for production or live-capital
promotion.

However, the reserve independently reproduced the direction of the previously
observed ATR effect:

    - candidate improved total P&L relative to control
    - 6 / 8 assets beat control
    - 7 / 8 assets were not worse
    - candidate trade count was lower
    - candidate median drawdown was lower

This occurred on data that played no role in discovering, selecting, or
freezing the ATR >= 0.005 challenger.

The strongest defensible conclusion is therefore:

    The range / volatility abstention phenomenon generalized.

    The current complete trading architecture did not demonstrate sufficient
    absolute economic edge across all observed regimes.

The result supports continued investigation of independent market-state
information rather than additional ATR-threshold optimization.


==============================================================================
31. RESEARCH CONSEQUENCES
==============================================================================

ATR >= 0.005 must NOT now be retuned using the 2026 reserve.

The following 2026 observations must not be used as optimization labels:

    - aggregate candidate loss
    - aggregate candidate-control delta
    - ETH deterioration
    - ADA profitability
    - individual 2026 trades
    - asset-specific 2026 outcomes

The 2026 period may be cited as terminal evidence about the frozen challenger,
but it is no longer valid unseen development or validation data.

Future strategy development should return to the existing development corpus
and use genuinely new future data for later independent validation.


==============================================================================
32. RANGE + ATR RESEARCH MILESTONE CLOSURE
==============================================================================

Coinbase USD Universe V1:               FROZEN
Adaptive range component:               SUPPORTED
Universal ATR >= 0.005 phenomenon:      GENERALIZED
Development profitability:              POSITIVE
Structural robustness:                  PASS
Relative high-cost robustness:          PASS
Absolute high-cost profitability:       FAIL
2026 absolute profitability:            FAIL
2026 relative generalization:           PASS
Production approval:                    NO
Live-capital approval:                  NO
2026 reserve:                           CONSUMED PERMANENTLY

The current range + ATR research chapter is therefore closed as:

    USEFUL EMPIRICAL COMPONENT DISCOVERED
    BUT INSUFFICIENT COMPLETE TRADING EDGE

The next research mission should investigate an independent information axis
capable of identifying adverse opportunity regimes not captured by range and
ATR alone.

The leading next mission is:

    EVENT-RISK / GEOPOLITICAL REGIME RESEARCH

Event-Risk remains disconnected from the production/live strategy until that
research mission is separately designed, agreed, implemented, and validated.
