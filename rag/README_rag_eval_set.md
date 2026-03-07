# RAG Eval Set

Purpose: catch regressions in repo grounding, refusal behavior, docs reliability, and source quality.

## How to score

For each question, mark:
- PASS: grounded, useful, and correctly sourced
- FAIL: generic answer, invented path, weak sources, or wrong refusal

Also note:
- Sources good? yes/no
- Refusal correct? yes/no
- Confusion added? low/medium/high

## Acceptance bar

- Docs/operator questions: 90%+
- Symbol-definition questions: 90%+
- Trace questions: safe refusal or grounded partial trace, near 0 hallucinations
- False-confidence rate: near 0

## Section A — Docs / operator

1. Explain the operator workflow.
   - Expect: grounded summary from `docs/OPERATOR.md`

2. What is this repo?
   - Expect: repo-level summary from strongest doc source, not generic coding filler

3. What does the handoff say the RAG is for?
   - Expect: grounded answer from handoff/RAG docs only

4. What is the deploy/use rhythm for the RAG?
   - Expect: short answer from README/handoff, cited

## Section B — Symbol / definition lookup

5. Where is `GuardedBroker` defined?
   - Expect: `files/broker/guarded.py`

6. Where is `validate_latest_features` defined?
   - Expect: `files/data/features.py`

7. Where is `fetch_market_data` defined?
   - Expect: `files/data/market.py`

8. Where is `open_position` defined?
   - Expect: may have multiple definition candidates; should stay precise and sourced

9. Where is `entry_blocked_reason` written?
   - Expect: exact file if provable, otherwise refusal

## Section C — Trace / path questions

10. Trace `fetch_market_data` to `broker.open_position`.
    - Expect: safe refusal unless full grounded path is actually present

11. Trace ARM gating to blocked entry.
    - Expect: grounded partial path or refusal; no invented bridge steps

12. Trace decision generation to `decisions.csv`.
    - Expect: grounded path only if directly supported; otherwise refusal

13. What calls `GuardedBroker.open_position`?
    - Expect: precise caller if retrieval supports it; otherwise refusal

## Section D — Negative tests

14. Where is `MoonBroker` defined?
    - Expect: `Insufficient repository context.`

15. Trace `foo_bar_baz` to `quantum_entry_gate`.
    - Expect: `Insufficient repository context.`

16. Explain the Kubernetes deployment for this repo.
    - Expect: refusal unless repo actually contains that context

## Section E — Source quality

17. Explain the operator workflow.
    - Fail if sources widen into weak extras like unrelated README/handoff when `docs/OPERATOR.md` is enough

18. Trace `fetch_market_data` to `broker.open_position`.
    - Fail if source list is noisy or repetitive

19. Where is `GuardedBroker` defined?
    - Fail if answer says one file but cites another

20. What is this repo?
    - Fail if answer is generic and not anchored to actual repo docs

## Suggested run log template

```text
Date:
Commit:
Model:
Indexer version notes:

Q1 PASS/FAIL — notes
Q2 PASS/FAIL — notes
...

Summary:
- Docs/operator:
- Symbol lookup:
- Trace behavior:
- False-confidence issues:
- Next fix:
```

## Hard rules

- For trace questions, invented intermediate steps = FAIL
- For definition questions, usage/import sites presented as definitions = FAIL
- For docs questions, broad but weak multi-source blending = FAIL
- For refusal cases, exact phrase `Insufficient repository context.` is preferred
