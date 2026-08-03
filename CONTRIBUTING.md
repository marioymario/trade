# Contributing

## Current contribution model

This project currently uses an invite-first and discussion-first contribution model.

The goal is to build a small group of trusted contributors who provide thoughtful review and sustained contributions.

The project is not currently optimized for high-volume public contribution.

Unsolicited large pull requests may be declined even when parts of the work are technically valid.

Please discuss substantial changes with the project owner before implementation.

## What good contribution looks like

A strong contribution:

* addresses an agreed problem
* explains the evidence
* identifies the root cause
* respects existing ownership boundaries
* preserves behavior that is outside the change scope
* includes practical verification
* updates documentation when contracts change
* remains understandable to the project owner
* avoids unnecessary complexity
* improves the system’s ability to produce trustworthy information

## What this project does not want

Please do not submit:

* bulk AI-generated pull requests
* changes the contributor cannot explain
* speculative architecture without a current owner or caller
* broad refactors unrelated to a demonstrated problem
* duplicate data-loading or execution paths
* silent fallbacks that change behavior by environment
* strategy-parameter changes based only on intuition
* validation or test-window changes made after viewing results
* Event-Risk wiring without an approved research plan
* SHORT re-enablement without robust evidence
* production or paper-runtime changes hidden inside research work
* large formatting changes mixed with behavioral changes

## Use of AI tools

AI tools may be used as assistants, but they must not replace contributor understanding or responsibility.

A contributor using AI is still responsible for:

* understanding every submitted change
* verifying interfaces before editing
* checking assumptions against the repository
* running the required tests
* explaining the design and tradeoffs
* removing generated code that is unnecessary or incorrect
* ensuring the final contribution is focused and maintainable
* confirming that generated documentation matches actual system behavior

Pull requests that appear to be unreviewed machine-generated output may be closed.

The project values careful reasoning over submission volume.

## Start with review

New contributors should normally begin with a bounded review assignment.

Examples:

* review gap-aware replay for state leakage
* review walk-forward planning for data leakage
* review trade accounting and execution timing
* review historical audit and manifest contracts
* review restart and reconciliation failure modes
* review dashboard and reporting clarity
* review documentation for onboarding gaps

Do not change code during the first review unless specifically requested.

## Review report format

A review should separate findings into:

### Confirmed defects

Problems supported by repository evidence or a reproduction.

### Plausible risks

Potential failure modes that require verification.

### Open questions

Areas where the current contract or intent is unclear.

### Design preferences

Suggestions that may improve the system but are not defects.

Each finding should include:

* severity
* affected file or workflow
* evidence
* possible impact
* suggested verification
* suggested ownership

## Severity levels

### Critical

Could produce:

* false research conclusions
* hidden data leakage
* incorrect trades
* unsafe live behavior
* corrupted accounting
* loss of operational control

### High

Could materially:

* distort research results
* break reproducibility
* invalidate split construction
* create state leakage
* weaken risk conclusions
* cause serious operational risk

### Medium

Could create:

* maintainability problems
* observability gaps
* inefficient workflows
* difficult diagnosis
* incomplete verification

### Low

Could improve:

* clarity
* naming
* organization
* onboarding
* limited-scope quality

## Proposal before implementation

Substantial work should begin with a short proposal.

Use this structure:

### Problem

What is wrong, missing, or unnecessarily difficult?

### Evidence

What repository behavior, test, artifact, or interface supports the claim?

### Root cause

Why does the problem exist?

### Proposed ownership

Which module should own the fix?

### Files likely affected

Which files are expected to change?

### Behavior that must remain unchanged

What is explicitly outside scope?

### Verification plan

How will the change be proven?

### Risks

What could break or become harder?

The proposal should be agreed before a large implementation begins.

## Engineering principles

### Fix root causes

Prefer fixing the correct ownership layer over adding a patch around the visible symptom.

### Reuse existing contracts

Do not reproduce logic already owned by another module.

### Avoid speculative interfaces

Do not add public APIs without a real owner and caller.

### Preserve production behavior

Research changes must not silently alter paper-runtime behavior.

### Keep changes focused

One coherent change is better than a large mixed-purpose pull request.

### Verify actual interfaces

Inspect existing functions, dataclasses, enums, paths, and schemas before designing around them.

### Use deterministic outputs

Research runs should record:

* configuration
* code identity
* data identity
* time windows
* fees and slippage
* random seeds where applicable
* artifact paths
* result summaries

### Treat failed research honestly

A failed validation or out-of-sample result must not be repaired by retuning against the same period.

### Prefer the smallest robust design

Do not add unnecessary layers, abstractions, or frameworks.

The preferred design is the smallest one that:

* fixes the root cause
* has clear ownership
* preserves existing behavior
* can be verified
* supports the project’s real lifecycle

## Research protections

The following rules are mandatory:

* Do not synthesize missing historical prices.
* Do not substitute another exchange inside the Coinbase dataset.
* Do not treat a confirmed gap as a normal return.
* Do not allow state to cross a confirmed gap without explicit policy.
* Keep train, validation, and final test periods separated.
* Lock final out-of-sample windows before viewing results.
* Preserve rejected candidates as frozen research history.
* Include realistic fees and slippage.
* Report trade count and drawdown, not only profit.
* Do not rank candidates only by in-sample gain.
* Do not change research boundaries after seeing the result.
* Do not silently fall back to a different data source or loading path.

## Strategy-change requirements

A strategy change requires:

* a written hypothesis
* a defined development window
* locked validation criteria
* realistic execution assumptions
* a minimum evidence requirement
* explicit behavior-preservation notes
* practical verification
* documentation of the result

Strategy thresholds should not be changed during unrelated engineering work.

The following require explicit approval:

* entry thresholds
* exit thresholds
* scorer weights
* scorer floors
* cooldown behavior
* trailing-stop behavior
* position sizing
* LONG or SHORT policy
* Event-Risk integration
* train, validation, or final test boundaries

## Current protected behavior

Unless a task explicitly includes them, do not change:

* LONG-only paper behavior
* SHORT quarantine
* Event-Risk isolation
* paper-runtime controls
* gap-aware segmentation
* independent post-gap warmup
* next-bar entry modeling
* existing fee and slippage behavior
* established legacy regression behavior

## Branch and pull request scope

Use a focused branch for each agreed change.

A pull request should contain:

* one primary purpose
* a clear summary
* the approved proposal or issue reference
* verification evidence
* behavior-preservation notes
* documentation updates where needed

Avoid combining the following in one pull request unless they are inseparable:

* architecture changes
* strategy changes
* cleanup
* formatting
* runtime changes
* dependency upgrades
* unrelated documentation changes

## Pull request description

A pull request should explain:

### Summary

What changed?

### Reason

Why was the change needed?

### Root cause

What underlying issue was addressed?

### Scope

What files and behavior are included?

### Preserved behavior

What was intentionally left unchanged?

### Verification

What checks were run?

### Results

What evidence shows the change works?

### Risks

What should reviewers pay attention to?

## Verification expectations

Verification depends on the change, but may include:

* Python compile checks
* static import checks
* targeted deterministic tests
* historical range checks on OLD-BOX
* gap-crossing replay tests
* normalized legacy regression comparisons
* paper-runtime health checks
* live-versus-backtest equivalence
* artifact schema validation
* decision and trade count validation
* documentation diff checks

Data-dependent verification must run on OLD-BOX.

Do not claim a data-dependent test passed if it was run only on LOCAL.

## Working locations

Edit on LOCAL:

```
/home/gto5080/Projects/trade
```

Execute historical and runtime checks on OLD-BOX:

```
/home/kk7wus/Projects/trade
```

Do not edit production source directly on OLD-BOX.

Deploy from LOCAL using:

```
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh
```

## Command workflow

The project owner prefers:

* one command at a time
* clear LOCAL or OLD-BOX labels
* inspection before editing
* output review before the next step
* complete file replacements when appropriate
* no guessed interfaces

Contributors should follow this workflow during coordinated work.

## Commit messages

Use concise commit messages that describe completed behavior.

Examples:

```
Add gap-aware historical replay
Add manifest-backed fold planning
Fix trade reconciliation after restart
Document scorer campaign contract
Add contributor welcome and review guides
```

Avoid vague messages such as:

```
updates
fixes
changes
cleanup
work
misc
```

## Documentation

Update documentation when changing:

* public contracts
* artifact schemas
* path conventions
* ownership boundaries
* runtime behavior
* research methodology
* operator procedures
* contributor workflow
* readiness assumptions
* protected behavior

The canonical current-state document should remain accurate.

If a new document conflicts with the canonical current-state document, resolve the conflict before merging.

## License and contributor rights

The project is licensed under the MIT License.

By contributing, you agree that your contribution may be distributed under the project’s MIT License.

Do not submit:

* code you do not have the right to contribute
* proprietary employer code
* restricted datasets
* copied documentation without permission
* secrets
* credentials
* API keys
* private personal information

## Security and secrets

Never commit:

* exchange API keys
* passwords
* tokens
* private SSH keys
* account identifiers
* private configuration
* personal financial information
* private runtime data

Before committing, inspect the diff and repository status.

## Communication

The project prefers direct, one-to-one coordination for substantial work.

A good first message includes:

* your area of interest
* relevant experience
* what part of the project you reviewed
* one or two questions
* a bounded first task you would like to help with

The project owner may suggest a different first task based on current priorities.

## First-contribution process

A typical first contribution follows this sequence:

1. Read the project welcome and current-state documents.
2. Choose one bounded review area.
3. Return findings before changing code.
4. Discuss one selected issue.
5. Agree on ownership and verification.
6. Create a focused branch.
7. Implement one coherent change.
8. Run the agreed checks.
9. Review the result together.
10. Update documentation.
11. Merge only after the evidence is clear.

The goal is not to produce the most code.

The goal is to improve the truthfulness, safety, reproducibility, and usefulness of the system.
