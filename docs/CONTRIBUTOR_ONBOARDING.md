# Contributor Onboarding

## Purpose

This guide helps invited contributors understand how to begin working with the project safely and productively.

The goal is not to make a new contributor productive as fast as possible at any cost.

The goal is to help each contributor:

* understand the project’s purpose
* understand what is proven and what is not
* learn the system boundaries
* avoid changing protected behavior accidentally
* review before editing
* make one focused and verifiable contribution
* communicate clearly with the project owner

The preferred contribution model is thoughtful, one-to-one collaboration.

## Contribution model

This project currently uses an invite-first and discussion-first contribution model.

Contributors are expected to:

* understand the area they are reviewing
* ask focused questions
* explain proposed changes
* fix root causes when possible
* respect existing ownership boundaries
* verify actual repository interfaces
* preserve unrelated behavior
* provide evidence
* remain responsible for all submitted work

The project is not seeking:

* high-volume public contribution
* bulk AI-generated pull requests
* unsolicited large rewrites
* strategy changes based only on intuition
* broad cleanup without a demonstrated need
* changes the contributor cannot explain
* architectural complexity without a real owner and caller

## What this project is

This project is a trading-research and paper-execution system.

Its purpose is to determine whether a strategy can demonstrate a repeatable, risk-controlled edge under realistic historical and forward-testing conditions.

The project includes:

* historical data validation
* gap-aware replay
* backtesting
* scorer research
* walk-forward planning
* paper execution
* runtime health controls
* observability
* an isolated Event-Risk service

Profitability is not proven.

The system is not ready for meaningful real-money execution.

A valid project outcome may be that a candidate strategy should not advance.

## What success means

Success does not mean producing the most code.

Success means improving one or more of the following:

* research truthfulness
* reproducibility
* data quality
* execution correctness
* observability
* operational safety
* contributor understanding
* confidence in rejecting weak candidates
* confidence in advancing strong candidates

A review that finds no defect may still be useful.

A decision not to implement a proposed feature may also be useful.

## Recommended reading order

Read these documents in this order:

1. README.md
2. CONTRIBUTING.md
3. docs/CANONICAL_CURRENT_STATE.md
4. docs/ARCHITECTURE.md
5. docs/RESEARCH_PRINCIPLES.md
6. docs/PROJECT_REVIEW_GUIDE.md
7. docs/research/historical_backfill_mission_2022_2026.md
8. ROADMAP.md

The canonical current-state document is the primary source of current project truth.

When older documents conflict with it, the canonical current-state document takes priority.

## Current project status

The historical replay foundation is complete enough for disciplined research.

The current audited historical contract includes:

* Coinbase BTC/USD
* 5-minute bars
* January 2022 through early February 2026
* 431,842 stored bars
* 158 confirmed missing bars
* seven confirmed Coinbase outages
* eight physical replay segments

The gap-aware replay implementation was committed as:

```
d4c6f7d Add gap-aware historical replay
```

The next major mission is manifest-backed walk-forward scorer planning.

## Current protected behavior

Unless a task explicitly includes these areas, do not change:

* LONG-only paper behavior
* SHORT quarantine
* Event-Risk isolation
* paper-runtime controls
* gap-aware segmentation
* independent post-gap warmup
* next-bar entry modeling
* trailing-stop ordering
* fee and slippage behavior
* decision and trade schemas
* legacy regression behavior
* final out-of-sample boundaries
* strategy thresholds
* scorer parameters

Protected behavior may be reviewed.

It should not be changed casually.

## Machine roles

The project uses two machines with separate responsibilities.

## LOCAL

Repository:

```
/home/gto5080/Projects/trade
```

LOCAL is used for:

* source editing
* Git
* documentation
* design
* reviewing code
* preparing changes
* deployment

LOCAL must not be used for:

* historical backtests
* data-dependent research execution
* scorer campaigns
* paper-runtime validation
* production-like testing

## OLD-BOX

Repository and runtime directory:

```
/home/kk7wus/Projects/trade
```

OLD-BOX is used for:

* historical data
* backtests
* scorer research
* paper runtime
* dashboard runtime
* Jupyter
* runtime health checks
* data-dependent verification

OLD-BOX is not the source-control authority.

Do not edit source directly on OLD-BOX unless the project owner explicitly directs it for an emergency investigation.

Normal changes must be made on LOCAL and deployed.

## Git ownership

Git truth exists on:

* LOCAL
* GitHub

OLD-BOX is an execution target.

A contributor should not treat OLD-BOX as a separate development branch.

Before beginning work, confirm:

* current branch
* current commit
* repository status
* task scope

Typical inspection commands on LOCAL:

```
cd ~/Projects/trade

git status --short

git branch --show-current

git log -1 --oneline
```

Do not begin editing when unrelated uncommitted changes are present without discussing them first.

## Deployment

Canonical deployment command from LOCAL:

```
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh
```

Deployment uses rsync.

It preserves runtime-owned files and excludes items such as:

* .git
* .env
* data
* caches
* local virtual environments
* runtime logs

Do not manually copy random files to OLD-BOX when the deployment script already owns that workflow.

## Command workflow

The project owner prefers:

* one command at a time
* commands labeled LOCAL or OLD-BOX
* inspection before editing
* output review before continuing
* no guessed interfaces
* complete files when appropriate
* clear verification after each step

During coordinated work, follow that pace.

Do not send a large sequence of commands that hides which step failed.

## First-day expectations

A new contributor should not begin by modifying code.

The first day should normally include:

1. Read the recommended documents.
2. Understand LOCAL and OLD-BOX responsibilities.
3. Choose one bounded review area.
4. Inspect the relevant modules.
5. Return findings before proposing a patch.
6. Separate defects, risks, questions, and preferences.
7. Discuss one possible contribution with the project owner.

## Choose one review area

Good first review areas include:

* gap-aware replay
* historical data quality
* walk-forward validity
* scorer research
* trade accounting
* state isolation
* observability
* operational safety
* documentation

Do not attempt to review the entire repository as a first task.

## Suggested first assignments

## Gap-aware replay review

Review:

* physical segment construction
* feature warmup
* entry cancellation
* forced exit behavior
* state reset
* boundary events

Primary files:

```
files/research/historical_dataset.py
files/backtest/replay.py
files/backtest/segment_executor.py
files/backtest/engine.py
files/research/execution_events.py
files/broker/paper.py
```

Do not modify code during the first review.

## Walk-forward review

Review:

* current fold definitions
* private engine imports
* source contracts
* gap awareness
* half-open ranges
* fold statistics
* validation boundaries
* final test protection

Primary files:

```
files/research/scorer_walk_forward.py
files/research/scorer_trial.py
files/research/scorer_search_config.py
files/research/scorer_parameter_space.py
files/research/historical_dataset.py
```

Do not modify code during the first review.

## Trade-accounting review

Review:

* fees
* slippage
* realized PnL
* cumulative PnL
* trade count
* stop prices
* exit reasons
* duplicate closing
* unresolved positions

Primary files:

```
files/broker/paper.py
files/data/trades.py
files/backtest/segment_executor.py
files/backtest/engine.py
```

Do not modify code during the first review.

## Observability review

Review:

* decision fields
* trade fields
* blocked reasons
* event artifacts
* dashboard summaries
* error messages
* runtime status

Primary files:

```
files/data/decisions.py
files/data/trades.py
files/research/execution_events.py
files/dashboard
files/main.py
```

Do not redesign the entire dashboard during the first review.

## Operational safety review

Review:

* restart behavior
* STOP, HALT, and ARM controls
* duplicate protection
* stale data
* daily loss controls
* position controls
* future exchange reconciliation
* partial-fill handling
* cancel failures

Primary areas:

```
files/main.py
files/broker/paper.py
ops
docker-compose.yml
runtime configuration documentation
```

Do not add live order execution during the first review.

## How to inspect the repository

Start with filenames and ownership.

Useful LOCAL commands include:

```
cd ~/Projects/trade

find files -maxdepth 3 -type f | sort

find docs -maxdepth 3 -type f | sort

rg "function_or_class_name" files

rg "_load_all_ohlcv_parquet" files

git log --oneline --decorate -20
```

Use focused searches.

Do not read every file without a clear review question.

## Verify interfaces before designing

Before proposing a change, inspect:

* function signatures
* dataclasses
* enums
* schemas
* paths
* callers
* return values
* side effects
* existing verification scripts

Do not design around assumed interfaces.

If a function is private, determine:

* who calls it
* why it is private
* whether a public contract already exists
* whether the real defect is missing ownership

## Review report

A first review should contain:

### Scope

What area was reviewed?

### Files inspected

Which files were examined?

### Confirmed defects

What was proven to be wrong?

### Plausible risks

What might fail but still requires verification?

### Open questions

What intent or contract remains unclear?

### Design preferences

What might improve the design but is not a correctness problem?

### Recommended next action

What is the smallest useful next step?

Each finding should include:

* severity
* evidence
* potential impact
* suggested verification
* suggested ownership

## Before proposing implementation

A contributor should be able to explain:

* the problem
* the evidence
* the root cause
* the correct owner
* the expected behavior
* the behavior that must remain unchanged
* the verification plan
* the risks

If those points are unclear, implementation should wait.

## Change proposal format

Use this structure:

### Problem

Describe the problem.

### Evidence

Provide repository or runtime evidence.

### Root cause

Explain why the problem exists.

### Proposed ownership

Identify the module that should own the fix.

### Files likely affected

List the expected files.

### Behavior that must remain unchanged

List protected behavior.

### Verification plan

Describe how correctness will be proven.

### Risks

Describe possible regressions or uncertainty.

## Branch workflow

After a proposal is agreed, create a focused branch.

Example:

```
cd ~/Projects/trade

git switch -c contributor/walk-forward-source-contract
```

Use a branch name that describes the task.

Do not combine unrelated work in one branch.

Before editing, verify:

```
git status --short

git branch --show-current
```

## Editing rules

Make changes on LOCAL.

Keep the change focused.

Avoid unrelated:

* formatting
* renaming
* cleanup
* dependency upgrades
* strategy changes
* architecture changes

Do not edit a large file merely to make it match a personal style preference.

## Documentation rules

Update documentation when changing:

* public interfaces
* ownership
* path contracts
* artifact schemas
* runtime behavior
* research methodology
* contributor workflow
* operator procedures

Do not update documentation to describe behavior that has not been implemented and verified.

Future design should be clearly labeled as planned.

## Testing and verification

Data-independent checks may run on LOCAL.

Examples:

```
cd ~/Projects/trade

python3 -m compileall -q files

git diff --check
```

Data-dependent checks must run on OLD-BOX.

Examples include:

* historical audits
* backtests
* scorer trials
* gap-crossing execution
* paper-runtime validation
* artifact comparisons

Do not report a data-dependent result from LOCAL as proof.

## Deployment for verification

After LOCAL checks pass, deploy to OLD-BOX:

```
cd ~/Projects/trade

OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh
```

Then run only the targeted OLD-BOX verification required for the change.

Do not rerun the complete four-year backtest unless the change requires it.

## Regression expectations

When behavior should remain unchanged, compare against an established baseline.

Possible comparisons include:

* decision counts
* trade counts
* normalized decision hashes
* normalized trade hashes
* event artifact contents
* first eligible decision timestamp
* gap exclusion
* broker state
* cumulative PnL
* live-versus-backtest behavior

Do not use raw hashes when expected namespace fields differ.

Normalize only fields known to differ by run identity.

## Commit expectations

Before committing:

```
cd ~/Projects/trade

git status --short

git diff --check

git diff --stat

git diff
```

The contributor should understand every changed line.

Suggested commit style:

```
Add manifest-backed fold planning

Fix gap-boundary validation

Document scorer campaign contract
```

Avoid vague commit messages such as:

```
fixes

updates

cleanup
```

## Pull request expectations

A pull request should explain:

* what changed
* why it changed
* root cause
* affected files
* preserved behavior
* verification performed
* results
* risks
* documentation changes

A pull request should have one primary purpose.

Large generated descriptions should be edited into a concise and accurate explanation.

## AI tool expectations

AI tools may help with:

* code explanation
* test ideas
* documentation drafting
* identifying possible failure cases
* reviewing a proposed contract

AI tools must not replace:

* repository inspection
* contributor understanding
* verification
* responsibility
* human review

A contributor must be able to explain every submitted change without relying on the AI conversation.

Do not submit raw AI output as a pull request.

## Secrets and private information

Never commit:

* exchange API keys
* passwords
* access tokens
* private SSH keys
* private account details
* personal financial information
* private runtime configuration
* sensitive logs
* .env files

Before pushing, inspect the diff carefully.

If a secret is committed, notify the project owner immediately.

Deleting it in a later commit may not remove it from Git history.

## Research integrity

Contributors must not:

* move validation windows after viewing results
* tune against the final test period
* hide losing folds
* omit realistic costs
* synthesize missing data
* substitute another exchange silently
* select only favorable results
* present paper results as guaranteed live results
* change strategy behavior during an infrastructure regression test

A failed result must remain visible.

## Communication style

Useful communication is:

* direct
* specific
* evidence-based
* open about uncertainty
* respectful of scope
* clear about whether something is fact, risk, question, or preference

A useful message might say:

```
I found a possible state leak in files/broker/paper.py.

I have not reproduced it yet.

The concern is that cooldown may survive a segment reset.

I suggest a deterministic two-segment test before changing code.
```

An unhelpful message might say:

```
The broker architecture is bad and should be rewritten.
```

## When to stop

Stop and discuss before continuing when:

* the current interface differs from the proposal
* unrelated changes are discovered
* a protected behavior appears affected
* a test fails unexpectedly
* OLD-BOX data differs from assumptions
* the scope expands
* the root cause becomes unclear
* the proposed owner appears wrong

Do not continue adding patches around an unclear failure.

## Contributor access

Access should be granted gradually.

A new contributor may begin with:

* repository read access
* review assignments
* issue discussion
* a focused branch
* a small pull request

Broader access should follow demonstrated understanding, reliability, and sustained contribution.

## First contribution checklist

Before the first pull request, confirm:

* recommended documents read
* one bounded task agreed
* relevant interfaces inspected
* root cause identified
* protected behavior listed
* verification plan agreed
* changes made on LOCAL
* data-dependent checks run on OLD-BOX
* documentation updated if needed
* diff reviewed
* no secrets included
* commit message is specific

## First-week goal

The goal of the first week is not to make a large change.

A successful first week may produce:

* a strong review report
* one confirmed defect
* one targeted deterministic test
* one documentation improvement
* one small root-cause fix
* clearer ownership
* a decision that no code change is needed

## Long-term contribution

Sustained contributors may eventually own areas such as:

* research methodology
* historical data integrity
* scorer campaigns
* backtest correctness
* observability
* operations
* exchange execution safety
* documentation

Ownership means responsibility for:

* understanding contracts
* reviewing changes
* preserving behavior
* maintaining documentation
* verifying results
* communicating risks

Ownership does not mean making changes without review.

## Final principle

The project values trustworthy progress over fast progress.

The best first contribution is one that demonstrates:

* careful understanding
* clear evidence
* correct ownership
* focused implementation
* reliable verification

The objective is not merely to make the system larger.

The objective is to make the system more truthful, safe, reproducible, and informative.
