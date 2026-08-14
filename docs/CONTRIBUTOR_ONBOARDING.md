# Contributor Onboarding

## Purpose

This guide explains how to begin contributing safely and productively.

It is intentionally concise.

It does not duplicate:
- the active mission
- system architecture
- research history
- campaign results
- detailed review methodology

Those subjects have separate document owners.

The goal of onboarding is to help a contributor understand:

- what the project is trying to prove
- where current truth lives
- which behaviors are protected
- how LOCAL and OLD-BOX responsibilities differ
- how to inspect before editing
- how to verify changes
- how to make one focused contribution

The preferred contribution model is thoughtful, bounded, and
evidence-driven.

--------------------------------------------------
1) WHAT THIS PROJECT IS
--------------------------------------------------

This is a trading-research and paper-execution system.

Its purpose is to determine whether a strategy/scorer family can
demonstrate repeatable, risk-controlled out-of-sample profitability
after realistic costs.

The project includes:

- live paper execution
- historical data acquisition and auditing
- manifest-backed gap-aware replay
- chronological walk-forward research
- deterministic scorer campaigns
- multi-asset research
- runtime health and operator controls
- observability
- an isolated Event-Risk service

Profitability is not proven.

The system is not approved for meaningful real-money execution.

Rejecting a weak candidate is a successful research outcome.

--------------------------------------------------
2) WHERE CURRENT TRUTH LIVES
--------------------------------------------------

Use documents according to ownership.

`HANDOFF.md`

Read first.

Owns:
- active mission
- exact current research branch and commit
- current campaign/run state
- immediate next action
- transient information needed to continue work


`docs/CANONICAL_CURRENT_STATE.md`

Owns:
- durable current system state
- machine roles
- safety boundaries
- research architecture
- frozen research populations
- protected boundaries
- documentation ownership


`docs/ARCHITECTURE.md`

Owns:
- module responsibilities
- interfaces
- data flows
- runtime architecture
- historical replay architecture
- campaign architecture


`docs/RESEARCH_PRINCIPLES.md`

Owns:
- evidence standards
- chronological validation
- out-of-sample protection
- gap policy
- reproducibility
- cross-asset comparison policy


`docs/PROJECT_REVIEW_GUIDE.md`

Owns:
- detailed review methodology
- how to report findings
- how to distinguish defects, risks, questions, and preferences


Contract documents

Own:
- exact subsystem behavior
- schemas
- failure semantics
- versioned interfaces


`docs/research/`

Contains research mission reports and diagnostics.


`docs/milestones/`

Contains completed immutable milestone reports.


Archive documents

`docs/ARCHIVE_handoffs.md`
`docs/ARCHIVE_project_snapshots.md`

These provide historical context only.

Do not use archived documents as current instructions.

--------------------------------------------------
3) RECOMMENDED READING ORDER
--------------------------------------------------

For a new contributor:

1. `HANDOFF.md`
2. `docs/CANONICAL_CURRENT_STATE.md`
3. `docs/ARCHITECTURE.md`
4. `docs/RESEARCH_PRINCIPLES.md`
5. `CONTRIBUTING.md`
6. `docs/PROJECT_REVIEW_GUIDE.md`

Then read only the subsystem contract or mission report relevant to the
assigned task.

Do not begin by reading every historical handoff.

--------------------------------------------------
4) CURRENT PROTECTED BEHAVIOR
--------------------------------------------------

Unless the task explicitly includes these areas, preserve:

- LONG_ONLY live/paper behavior
- SHORT quarantine
- Event-Risk isolation
- paper-only execution
- historical gap awareness
- independent post-gap warmup
- next-bar execution semantics
- stop/exit ordering
- fee and slippage semantics
- decision/trade contracts
- manifest-backed source identity
- frozen chronological validation folds
- protected 2025+ out-of-sample data
- legacy behavior where a research override is absent

Protected behavior may be reviewed.

It must not be changed casually.

--------------------------------------------------
5) MACHINE ROLES
--------------------------------------------------

The project intentionally separates editing from authoritative execution.

### LOCAL

Primary repository:

`/home/gto5080/Projects/trade`

Research worktrees may exist separately, including:

`/home/gto5080/Projects/trade-entry-quality`

LOCAL is used for:

- source editing
- Git
- documentation
- code review
- design
- lightweight static checks
- deployment preparation

LOCAL is not authoritative for:

- historical backtests
- pandas/data-dependent execution
- scorer campaigns
- historical-data validation
- runtime proof


### OLD-BOX

Canonical runtime:

`/home/kk7wus/Projects/trade`

Research staging may exist separately, including:

`/home/kk7wus/Projects/trade-entry-quality`

OLD-BOX is used for:

- historical datasets
- backtests
- research campaigns
- paper runtime
- dashboard
- Jupyter/tooling
- runtime health checks
- data-dependent verification

OLD-BOX is not the Git/source-control authority.

Normal source edits are made on LOCAL and deployed.

--------------------------------------------------
6) GIT AND WORKTREE DISCIPLINE
--------------------------------------------------

Before editing, confirm:

- working directory
- branch
- current commit
- worktree status
- task scope

Do not assume that `main` is the active research branch.

The active branch and exact checkpoint belong in `HANDOFF.md`.

Do not edit through unrelated uncommitted changes without discussing
them first.

Do not use OLD-BOX as a separate development branch.

Project source-control truth lives on LOCAL and GitHub.

--------------------------------------------------
7) DEPLOYMENT MODEL
--------------------------------------------------

Deployment is rsync-based through project tooling.

Runtime-owned state is excluded.

Examples include:

- `.git`
- `.env`
- `data/`
- caches
- local environments
- runtime logs

Do not manually copy random source files when the deployment helper owns
the workflow.

Research staging and canonical runtime are separate locations when the
current mission uses a research worktree.

Always confirm the destination before deploying.

--------------------------------------------------
8) REQUIRED ENGINEERING WORKFLOW
--------------------------------------------------

For behavior-changing work:

ADJUST
-> DEPLOY DIRTY
-> VERIFY ON OLD-BOX
-> FIX / REPEAT
-> COMMIT / PUSH
-> CLEAN DEPLOY
-> AUTHORITATIVE OLD-BOX VERIFY

This prevents unverified code from becoming the repository checkpoint.

LOCAL checks are useful but do not replace OLD-BOX proof when execution
depends on:

- pandas
- historical data
- Docker runtime dependencies
- campaign artifacts
- broker behavior
- historical replay

--------------------------------------------------
9) INSPECT BEFORE EDITING
--------------------------------------------------

Do not design against assumed interfaces.

Before changing a subsystem, inspect:

- function signatures
- dataclasses
- configuration objects
- enums
- schemas
- callers
- return values
- side effects
- artifact paths
- existing tests
- existing verification scripts

Search for existing ownership before introducing a new abstraction.

Prefer extending the smallest correct owner rather than duplicating
logic.

--------------------------------------------------
10) FIRST CONTRIBUTION
--------------------------------------------------

A new contributor should begin with one bounded area.

Good review areas include:

- historical-data integrity
- gap-aware replay
- walk-forward validity
- scorer campaigns
- trade accounting
- state isolation
- observability
- operational safety
- documentation
- automated regression coverage

The first task should normally be:

1. inspect
2. report findings
3. identify root cause or missing contract
4. agree on a bounded change
5. implement
6. verify
7. document if needed

Do not begin with a broad rewrite.

--------------------------------------------------
11) REVIEW REPORT FORMAT
--------------------------------------------------

Useful findings should distinguish:

FACT

What the current code or artifact actually does.


DEFECT

Behavior that violates an intended or documented contract.


RISK

Something that may fail or become unsafe but is not yet demonstrated as
a defect.


QUESTION

Something whose intended behavior is genuinely unclear.


PREFERENCE

A design alternative that is not required for correctness.

This separation prevents architectural preferences from being presented
as bugs.

--------------------------------------------------
12) RESEARCH INTEGRITY
--------------------------------------------------

Contributors must not:

- move validation windows after seeing results
- tune against protected final out-of-sample data
- hide losing folds
- omit realistic transaction costs
- fabricate missing candles
- substitute another exchange silently
- select only favorable results
- treat one profitable period as proof
- present paper results as guaranteed live results
- change strategy behavior during an infrastructure equivalence test
- compare raw cross-asset dollar PnL under unequal economic exposure

A failed result remains evidence.

Detailed policy lives in:

`docs/RESEARCH_PRINCIPLES.md`

--------------------------------------------------
13) CROSS-ASSET RESEARCH
--------------------------------------------------

The project contains a frozen Coinbase USD multi-asset research universe.

Do not assume BTC/USD is the only historical research source.

Do not assume all markets have equal historical completeness.

Each source retains its own:

- data tag
- manifest
- fingerprint
- gaps
- physical segments

When absolute capital-dependent results are compared across assets,
economic exposure must be comparable.

Research-only sizing controls must remain isolated from live sizing unless
explicitly promoted through a separate verified process.

--------------------------------------------------
14) TESTING AND VERIFICATION
--------------------------------------------------

Verification should match the change.

Possible checks include:

- syntax/static checks
- interface imports
- deterministic unit/regression tests
- artifact comparisons
- replay checks
- campaign planning checks
- narrow historical smoke tests
- full campaign execution when required

Do not rerun expensive historical campaigns merely because they exist.

Use the smallest test that proves the changed contract, then perform the
necessary authoritative verification.

When behavior should remain unchanged, compare against an established
baseline.

Possible comparisons include:

- decision counts
- trade counts
- normalized hashes
- event artifacts
- first eligible decision timestamp
- gap exclusion
- broker state
- PnL/accounting behavior

--------------------------------------------------
15) COMMIT EXPECTATIONS
--------------------------------------------------

Before committing:

- inspect `git status`
- run `git diff --check`
- review the diff
- understand every changed file
- confirm no secrets or runtime artifacts are included
- confirm required OLD-BOX verification has passed

Commit messages should state the actual change.

Avoid vague messages such as:

- fixes
- updates
- cleanup

Do not commit unverified behavior-changing work.

--------------------------------------------------
16) PULL REQUEST EXPECTATIONS
--------------------------------------------------

A pull request should explain:

- what changed
- why
- root cause
- affected ownership boundary
- preserved behavior
- verification performed
- results
- risks
- documentation changes

A pull request should have one primary purpose.

Generated descriptions should be edited into concise, accurate project
language.

--------------------------------------------------
17) AI TOOL EXPECTATIONS
--------------------------------------------------

AI tools may assist with:

- code explanation
- research questions
- test ideas
- documentation drafting
- failure-case analysis
- contract review

AI output does not replace:

- repository inspection
- contributor understanding
- execution verification
- human responsibility

A contributor must be able to explain submitted work without relying on
an AI conversation.

Do not submit raw generated output without review.

--------------------------------------------------
18) SECRETS AND PRIVATE INFORMATION
--------------------------------------------------

Never commit:

- exchange API keys
- passwords
- access tokens
- SSH private keys
- private account information
- personal financial information
- `.env` files
- sensitive runtime configuration
- sensitive logs

If a secret is committed, notify the project owner immediately.

A later deletion commit does not necessarily remove it from Git history.

--------------------------------------------------
19) WHEN TO STOP
--------------------------------------------------

Stop and discuss when:

- an actual interface differs from the planned change
- unrelated modifications appear
- protected behavior may be affected
- a verification fails unexpectedly
- OLD-BOX data differs from assumptions
- scope expands materially
- root cause becomes unclear
- ownership appears to belong in another module
- a proposed research change would expose protected OOS data

Do not layer patches around an unclear failure.

--------------------------------------------------
20) CONTRIBUTOR ACCESS AND OWNERSHIP
--------------------------------------------------

Access should increase with demonstrated understanding and reliability.

A contributor may begin with:

- repository review
- issue discussion
- a focused branch
- a bounded pull request

Sustained contributors may eventually own areas such as:

- research methodology
- historical-data integrity
- scorer campaigns
- backtest correctness
- observability
- operations
- execution safety
- documentation

Ownership means responsibility for:

- understanding contracts
- reviewing changes
- preserving behavior
- maintaining documentation
- verifying results
- communicating risk

Ownership does not mean making unreviewed changes.

--------------------------------------------------
21) FIRST-CONTRIBUTION CHECKLIST
--------------------------------------------------

Before a first pull request, confirm:

- current HANDOFF read
- canonical state read
- relevant architecture read
- one bounded task agreed
- relevant interfaces inspected
- root cause or contract identified
- protected behavior listed
- verification plan understood
- source changes made on LOCAL
- required data-dependent checks performed on OLD-BOX
- documentation updated where appropriate
- diff reviewed
- no secrets included
- commit message is specific

--------------------------------------------------
22) FINAL PRINCIPLE
--------------------------------------------------

Trustworthy progress matters more than fast progress.

The best contribution is not the largest one.

It is the one that:

- understands the current system
- respects ownership boundaries
- improves truthfulness or safety
- changes only what is necessary
- produces reproducible evidence
- leaves the next contributor with clearer information

The objective is not to make the project larger.

The objective is to make it more truthful, safe, reproducible, and useful
for determining whether a real trading edge exists.
