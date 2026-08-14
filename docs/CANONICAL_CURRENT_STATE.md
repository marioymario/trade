# CANONICAL CURRENT SYSTEM STATE — MJÖLNIR

Last structural review:
2026-08-13

This document describes the durable current state of the trading system.

It is authoritative for:
- machine and environment roles
- live/paper safety boundaries
- runtime architecture
- historical-data architecture
- research architecture
- frozen research populations and protected boundaries
- reproducibility expectations
- documentation ownership

It does NOT own:
- the currently running experiment
- the latest campaign results
- today's Git commit
- temporary PID or log state
- the next research mission

Those belong in the root HANDOFF.md and mission/milestone reports.

If documents disagree:

1. Exact technical contracts and executable code govern their own interfaces.
2. HANDOFF.md governs the active mission and current repository checkpoint.
3. This document governs durable current system state.
4. Research principles govern evidence and evaluation policy.
5. Archived handoffs and snapshots are historical only.

--------------------------------------------------
1) MISSION
--------------------------------------------------

Build a reliable, reproducible, observable paper-trading and research
system capable of discovering strategy and scorer configurations with
repeatable out-of-sample profitability and controlled risk after
realistic costs.

The main unresolved problem is proving a durable trading edge.

The project is not approved for real-money execution.

--------------------------------------------------
2) OPERATIONAL LAYERS
--------------------------------------------------

The system has two deliberately separated layers:

1. Live/paper runtime
2. Historical research

Research work must not casually alter live behavior.

Promotion of research behavior into the runtime requires an explicit,
separately verified decision.

--------------------------------------------------
3) MACHINE ROLES
--------------------------------------------------

LOCAL

Primary repository:
`/home/gto5080/Projects/trade`

Research worktrees may exist separately, including:
`/home/gto5080/Projects/trade-entry-quality`

LOCAL responsibilities:
- source editing
- Git
- documentation
- lightweight static checks
- research design
- deployment preparation

LOCAL is not the authoritative environment for:
- historical-data execution
- pandas-dependent validation
- backtests
- scorer campaigns
- data-dependent research proof


OLD-BOX

Canonical runtime:
`/home/kk7wus/Projects/trade`

Research staging worktrees may exist separately, including:
`/home/kk7wus/Projects/trade-entry-quality`

OLD-BOX responsibilities:
- live paper loop
- historical data
- backtests
- research campaigns
- dashboard
- Jupyter/tooling
- runtime-owned configuration
- practical dependency/data-aware verification

OLD-BOX is operational.

Project source-control truth remains on LOCAL/GitHub.

--------------------------------------------------
4) ENGINEERING AND DEPLOYMENT CONTRACT
--------------------------------------------------

Normal behavior-changing workflow:

ADJUST
-> DEPLOY DIRTY
-> VERIFY ON OLD-BOX
-> FIX / REPEAT
-> COMMIT / PUSH
-> CLEAN DEPLOY
-> AUTHORITATIVE OLD-BOX VERIFY

Do not commit behavior-changing work before practical OLD-BOX
verification.

Deployment is rsync-based.

Runtime-owned state must not be overwritten by source deployment,
including:
- `.env`
- historical/runtime `data/`
- operator flags
- generated logs
- caches

Do not rely on Git inside OLD-BOX as the runtime deployment mechanism.

Deployed source identity is recorded explicitly by deployment tooling.

--------------------------------------------------
5) LIVE / PAPER SAFETY BOUNDARY
--------------------------------------------------

Current live strategy policy:
- LONG_ONLY
- SHORT quarantined
- Event-Risk disconnected
- paper-only

Research code must preserve this boundary unless a future mission
explicitly changes it.

No current research result authorizes real-money execution.

--------------------------------------------------
6) LIVE RUNTIME MODEL
--------------------------------------------------

The live loop processes closed bars only.

Core invariants include:
- one decision per processed closed bar
- monotonic decision timestamps
- separate decision and trade artifacts
- restart-safe persisted state
- explicit operator controls
- risk and execution guardrails at the broker boundary

The paper broker is local-only and does not represent permission for
real-money execution.

Detailed runtime behavior belongs in architecture and operator-specific
documentation rather than in this state file.

--------------------------------------------------
7) HISTORICAL DATA ARCHITECTURE
--------------------------------------------------

Historical research uses audited canonical datasets.

Canonical raw-data concept:

`data/raw/{data_tag}/{SYMBOL_STORAGE}/{timeframe}/...`

Each research source records:
- exchange
- symbol
- timeframe
- data tag
- dataset bounds
- manifest identity
- confirmed gaps
- physical replay segments

Missing historical candles are never silently fabricated.

The system must not:
- synthesize missing prices
- interpolate gaps
- substitute another exchange
- treat multi-hour gaps as ordinary returns
- silently carry indicator state across confirmed gaps
- silently carry positions across confirmed gaps

--------------------------------------------------
8) GAP-AWARE REPLAY
--------------------------------------------------

Manifest-backed historical replay is implemented.

Core rules:
- requested ranges are chronological
- ranges are half-open
- confirmed gaps remain explicit
- physical segments replay independently
- indicator warmup does not cross gaps
- state cannot silently cross gaps
- pending entries cannot execute where no legal next bar exists
- positions at physical gap boundaries follow explicit boundary policy
- manifest-backed research does not silently fall back to legacy replay

Legacy replay behavior remains preserved where explicitly requested.

The detailed historical-source and gap contracts live in code and
manifest artifacts.

--------------------------------------------------
9) COINBASE USD RESEARCH UNIVERSE V1
--------------------------------------------------

Universe ID:

`research_universe_coinbase_usd_v1`

Universe fingerprint:

`f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a`

Status:

FROZEN

Membership:
29 Coinbase USD spot markets

Verification state:
- 29/29 members verified
- all deployed manifest hashes matched the frozen contract
- all canonical raw datasets existed
- no universe-build failures remained

Historical completeness varies materially across members.

This is intentional and explicit.

Sparse datasets are not repaired by inventing candles.

Material changes to membership or universe semantics require a new
universe version.

--------------------------------------------------
10) CURRENT COMPARABLE RESEARCH POPULATION
--------------------------------------------------

PRIMARY_COMPARABLE:

- BTC/USD
- ETH/USD
- SOL/USD
- ADA/USD
- XLM/USD
- LINK/USD
- DOGE/USD
- LTC/USD

Secondary population:

- DOT/USD
- BCH/USD
- SHIB/USD
- ATOM/USD

Population membership and eligibility policy must not be silently
changed after results are viewed.

--------------------------------------------------
11) CHRONOLOGICAL RESEARCH CONTRACT
--------------------------------------------------

Current frozen walk-forward structure:

Fold 1:
- train 2022
- validate 2023-H1

Fold 2:
- train through 2023-H1
- validate 2023-H2

Fold 3:
- train through 2023
- validate 2024

Ranges are half-open.

The 2025+ period remains protected out-of-sample data.

Protected OOS must not be inspected during ordinary parameter
development or candidate selection.

--------------------------------------------------
12) RESEARCH CAMPAIGN ARCHITECTURE
--------------------------------------------------

The deterministic scorer campaign system is implemented.

Capabilities include:
- manifest-backed source enforcement
- explicit scorer contracts
- deterministic candidate generation
- explicit candidate identity
- deterministic campaign identity
- chronological walk-forward planning
- train and validation execution
- isolated execution artifacts
- resume/reuse of valid completed work
- partial-failure preservation
- aggregation
- rejection policy
- ranking policy
- Git/source identity recording
- realistic transaction-cost scenarios

The historical source is resolved once per campaign process and reused
rather than repeatedly rediscovered.

--------------------------------------------------
13) CURRENT SCORER RESEARCH CONTRACT
--------------------------------------------------

The normalized-slope scorer contract exists for research:

`entry_scorer_v3_normalized_slope`

The absolute-slope scorer contract remains preserved for legacy/live
behavior where applicable.

Research contracts must not silently replace live/default behavior.

Candidate and campaign identity must capture every behavior-changing
research assumption that affects results.

--------------------------------------------------
14) CROSS-ASSET ECONOMIC COMPARABILITY
--------------------------------------------------

Cross-asset raw dollar PnL is only comparable when economic exposure is
comparable.

A fixed quantity of base asset is not sufficient.

The research system therefore supports an explicit optional research
order-notional contract:

`research_order_notional_usd`

When absent:
- legacy/default sizing behavior is preserved
- the field is omitted from legacy campaign identity

When supplied:
- research quantity is derived from the explicit USD exposure
- the behavior-changing value participates in campaign identity

This sizing control is research-only.

It does not alter live sizing unless separately promoted and verified.

Detailed evidence and current campaign use belong in HANDOFF.md or a
milestone report.

--------------------------------------------------
15) RESEARCH EVIDENCE POLICY
--------------------------------------------------

The research objective is not maximum in-sample profit.

Important evidence includes:
- out-of-sample profitability
- worst-fold performance
- cross-period consistency
- cross-asset consistency
- drawdown
- return-to-drawdown
- sufficient trade count
- transaction-cost robustness
- parameter stability
- winner concentration
- reproducibility

One profitable fold, one asset, one large winner, or high aggregate PnL
does not establish a robust edge.

Detailed evaluation rules live in:

`docs/RESEARCH_PRINCIPLES.md`

--------------------------------------------------
16) EVENT-RISK BOUNDARY
--------------------------------------------------

Event-Risk remains a separate research/service layer.

It is not currently wired into the live trading decision path.

It may be evaluated in a future controlled research mission.

Until explicitly changed:
- no live strategy dependence
- no hidden Event-Risk filtering
- no assumption that Event-Risk is active

--------------------------------------------------
17) REPRODUCIBILITY CONTRACT
--------------------------------------------------

Behavior-changing research must be reproducible from recorded identity.

Relevant identity may include:
- Git commit
- branch/deployed identity
- source data tag
- manifest fingerprint
- universe fingerprint
- population
- scorer contract
- trial identity
- strategy configuration
- sizing contract
- fee/slippage assumptions
- chronological folds
- rejection/ranking policy versions
- random seed
- artifact paths

Historical artifacts must not be silently overwritten with semantically
different results.

--------------------------------------------------
18) DOCUMENTATION OWNERSHIP
--------------------------------------------------

Root:

`HANDOFF.md`

Owns:
- active mission
- exact current branch/commit
- current running/completed campaign
- immediate next action
- transient operational context needed by the next explorer


`docs/CANONICAL_CURRENT_STATE.md`

Owns:
- durable current system state
- architecture-level boundaries
- frozen populations
- stable operational/research rules

It must not become a campaign diary.


`docs/ARCHITECTURE.md`

Owns:
- components
- module boundaries
- data flows
- runtime and research architecture
- architectural interfaces

It should not contain stale next-mission language.


`docs/RESEARCH_PRINCIPLES.md`

Owns:
- evidence standards
- chronological/OOS policy
- reproducibility principles
- comparison policy
- research integrity


Contract documents

Own:
- exact subsystem behavior
- schemas
- versioned interfaces
- failure semantics


`docs/research/`

Owns:
- research mission reports
- diagnostics
- completed hypothesis investigations


`docs/milestones/`

Owns:
- immutable completed milestone reports


`docs/ARCHIVE_handoffs.md`
`docs/ARCHIVE_project_snapshots.md`

Own:
- historical context only

Archive content does not define current truth.

--------------------------------------------------
19) NON-NEGOTIABLES
--------------------------------------------------

- Do not fabricate missing market data.
- Do not substitute another exchange to conceal source gaps.
- Do not silently cross confirmed historical gaps.
- Do not silently fall back from manifest-backed research.
- Do not change frozen validation windows after viewing results.
- Do not inspect protected OOS during ordinary candidate development.
- Do not treat notebook counterfactuals as engine proof.
- Do not use LOCAL for authoritative data-dependent execution.
- Do not overwrite OLD-BOX runtime-owned state during deployment.
- Do not casually alter live behavior from research work.
- SHORT remains quarantined.
- Event-Risk remains disconnected.
- Research remains paper-only.
- Historical results remain reproducible.
- Rejected candidates remain evidence.
- No real-money execution without robust out-of-sample evidence and
  separately verified execution safety.

--------------------------------------------------
20) CURRENT ASSESSMENT
--------------------------------------------------

The engineering and research infrastructure is substantially more mature
than the trading edge itself.

Established capabilities include:
- reliable paper runtime
- explicit operator controls
- audited historical datasets
- gap-aware replay
- frozen chronological folds
- deterministic scorer campaigns
- reproducible campaign identity
- multi-asset research universe
- explicit eligibility policy
- cross-asset comparable research sizing

The unresolved scientific question remains:

Can the strategy/scorer family produce repeatable, risk-controlled,
out-of-sample profitability across time and assets after realistic costs?

The active experiment addressing the current research phase is documented
in HANDOFF.md, not here.
