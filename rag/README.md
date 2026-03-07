# HANDOFF — Repo RAG Assistant

Purpose

This RAG exists to help with this repo using repo-grounded answers instead of generic coding knowledge.

It should:
- answer from repository context
- cite relevant source files
- refuse cleanly when support is weak
- help with docs and operator questions
- improve navigation speed without adding confusion

Hard rule:
if support is weak, say exactly:
Insufficient repository context.

## Current state

Current status:
- eval runner exists
- `./rag/rag.sh eval` works
- repo self-pollution from generated eval artifacts was addressed
- docs behavior is much stronger than before
- definition lookup is strong
- trace safety is strong
- multi-hop trace capability is still limited, but refusal discipline is good

Current known result:
- full eval has reached 20 PASS / 0 REVIEW / 0 FAIL
- after adding `./rag/rag.sh eval`, one handoff-related REVIEW may still appear sometimes depending on retrieval drift
- this should be treated as a small docs-ranking/source-selection wobble, not a trust failure

## Current stack

Runtime:
- Docker / Docker Compose
- Ollama on host
- model: qwen2.5-coder:14b
- embeddings: sentence-transformers/all-MiniLM-L6-v2
- vector store: Chroma
- interface: terminal prompt

Main files:
- rag/ingest_repo.py
- rag/query.py
- rag/rag.sh
- rag/eval_runner.py
- rag/README.md
- rag/HANDOFF.md
- docker-compose.rag.yml
- docker/rag.Dockerfile

## Commands

Start interactive prompt:
./rag/rag.sh

Ask one question:
./rag/rag.sh "Where is GuardedBroker defined?"

Rebuild index:
./rag/rag.sh index

Run full eval:
./rag/rag.sh eval

Run smaller eval:
./rag/rag.sh eval --limit 5

Show status:
./rag/rag.sh status

Show help:
./rag/rag.sh help

Direct eval runner still works:
python3 rag/eval_runner.py
python3 rag/eval_runner.py --limit 5

## What was fixed

Major fixes completed:
- added eval runner
- improved eval grading so correct answers are not falsely failed for formatting
- cleaned README so docs questions stop answering from eval-rubric text
- blocked retrieval pollution from generated artifacts
- fixed stale-vector issue by clearing vector DB contents correctly before rebuild
- blocked repo-scan fallback paths from re-reading eval output files
- improved docs source discipline
- improved refusal source quality
- added lightweight Python call-hint metadata during ingestion
- added `./rag/rag.sh eval` for easier workflow

## Working behavior

Good behavior:
- definition questions return exact files when supported
- docs questions prefer strong doc sources
- trace questions refuse when the bridge is not supported
- sources stay short and relevant
- negative tests refuse cleanly
- source lists are cleaner than before

Bad behavior:
- invented paths
- generic coding filler
- answering from weak or unrelated sources
- mixing usage sites with true definitions
- answering from generated artifacts
- fake source labels that are not actual repo file paths

## Current workflow

Use this rhythm:
1. pick one mission
2. identify exact file(s) first
3. make the smallest grounded change
4. re-index if ingestion changed
5. run proof questions
6. run eval
7. keep only changes that actually pass

## Operator rules for this RAG

Prefer:
- safe refusal over clever guessing
- exact definitions over broad explanation
- strongest doc over blended weak docs
- grounded partial trace over invented end-to-end trace

For trace questions:
- only name steps supported by retrieved repo context
- if the bridge is missing, refuse

For definition questions:
- definition evidence beats mentions or imports
- if multiple real candidates exist, say so clearly

For docs questions:
- prefer the strongest matching doc source
- avoid weak doc blends when one strong source is enough
- keep answers short and grounded

## Eval intent

The eval runner is the quality gate for this RAG.

It is used to catch regressions in:
- repo grounding
- refusal behavior
- docs reliability
- source quality
- trace safety

The eval should help answer:
- did trustworthiness improve?
- did source quality improve?
- did trace behavior stay safe?
- did we accidentally make docs answers worse?

## Current priorities

Top priorities:
1. keep trust high
2. improve docs reliability
3. improve trace ability without hallucination
4. keep source quality clean
5. keep terminal use simple

## Known weak area

Main weak area:
- multi-hop trace reconstruction is still limited

That is acceptable for now if refusal stays disciplined.

Important nuance:
- the system is strong at refusing unsafe traces
- it is not yet consistently strong at producing real grounded multi-hop traces

## Acceptance standard

This RAG is good when it:
- answers from repo context
- cites real source files
- refuses when support is weak
- helps with docs/operator questions reliably
- does not invent paths
- does not overclaim

If it invents paths, gives generic answers, or confidently blends weak sources, it is not ready.

## Next missions

Recommended order:
1. stabilize any remaining handoff/docs wobble so eval stays boring
2. improve real trace capability without increasing hallucination risk
3. keep `rag/rag.sh` operator surface clean and simple
4. optionally expand eval with a few tougher trace cases only after behavior is stable

## Notes

Re-index after meaningful repo or ingestion changes.

Do not let generated artifacts pollute retrieval.

Do not trust apparent improvements unless eval stays clean.

The goal is not to sound smart.
The goal is to be useful and trustworthy.
