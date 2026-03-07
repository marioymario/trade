#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    id: int
    section: str
    question: str
    expectation: str
    kind: str
    expected_sources: tuple[str, ...] = ()
    expected_phrases: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
RAG_SH = REPO_ROOT / "rag" / "rag.sh"


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        id=1,
        section="Docs / operator",
        question="Explain the operator workflow.",
        expectation="Grounded summary from docs/OPERATOR.md.",
        kind="docs_strong_source",
        expected_sources=("docs/OPERATOR.md",),
        forbidden_phrases=("README", "HANDOFF"),
    ),
    EvalCase(
        id=2,
        section="Docs / operator",
        question="What is this repo?",
        expectation="Repo-level summary from strongest doc source, not generic coding filler.",
        kind="docs_grounded",
        expected_sources=("rag/README.md", "README.md", "docs/", "HANDOFF"),
        forbidden_phrases=("microservices", "kubernetes", "distributed systems"),
    ),
    EvalCase(
        id=3,
        section="Docs / operator",
        question="What does the handoff say the RAG is for?",
        expectation="Grounded answer from handoff/RAG docs only.",
        kind="docs_grounded_or_refusal",
        expected_sources=("HANDOFF", "rag/README.md", "README.md", "docs/"),
    ),
    EvalCase(
        id=4,
        section="Docs / operator",
        question="What is the deploy/use rhythm for the RAG?",
        expectation="Short answer from README/handoff, cited.",
        kind="docs_grounded",
        expected_sources=("rag/README.md", "README.md", "HANDOFF", "docs/"),
    ),
    EvalCase(
        id=5,
        section="Symbol / definition lookup",
        question="Where is GuardedBroker defined?",
        expectation="files/broker/guarded.py",
        kind="definition_exact",
        expected_sources=("files/broker/guarded.py",),
        expected_phrases=("files/broker/guarded.py",),
    ),
    EvalCase(
        id=6,
        section="Symbol / definition lookup",
        question="Where is validate_latest_features defined?",
        expectation="files/data/features.py",
        kind="definition_exact",
        expected_sources=("files/data/features.py",),
        expected_phrases=("files/data/features.py",),
    ),
    EvalCase(
        id=7,
        section="Symbol / definition lookup",
        question="Where is fetch_market_data defined?",
        expectation="files/data/market.py",
        kind="definition_exact",
        expected_sources=("files/data/market.py",),
        expected_phrases=("files/data/market.py",),
    ),
    EvalCase(
        id=8,
        section="Symbol / definition lookup",
        question="Where is open_position defined?",
        expectation="Precise answer or disciplined multiple candidates.",
        kind="definition_flexible",
        expected_sources=("files/broker/",),
    ),
    EvalCase(
        id=9,
        section="Symbol / definition lookup",
        question="Where is entry_blocked_reason written?",
        expectation="Exact file if provable, otherwise refusal.",
        kind="definition_or_refusal",
        expected_sources=("files/",),
    ),
    EvalCase(
        id=10,
        section="Trace / path questions",
        question="Trace fetch_market_data to broker.open_position.",
        expectation="Safe refusal unless full grounded path is actually present.",
        kind="trace_safe",
        expected_sources=("files/data/market.py", "files/broker/"),
    ),
    EvalCase(
        id=11,
        section="Trace / path questions",
        question="Trace ARM gating to blocked entry.",
        expectation="Grounded partial path or refusal; no invented bridge steps.",
        kind="trace_safe",
        expected_sources=("files/", "docs/"),
    ),
    EvalCase(
        id=12,
        section="Trace / path questions",
        question="Trace decision generation to decisions.csv.",
        expectation="Grounded path only if directly supported; otherwise refusal.",
        kind="trace_safe",
        expected_sources=("files/main.py", "files/data/decisions.py", "decisions.csv"),
    ),
    EvalCase(
        id=13,
        section="Trace / path questions",
        question="What calls GuardedBroker.open_position?",
        expectation="Precise caller if supported; otherwise refusal.",
        kind="trace_safe",
        expected_sources=("files/broker/guarded.py", "files/main.py", "files/"),
    ),
    EvalCase(
        id=14,
        section="Negative tests",
        question="Where is MoonBroker defined?",
        expectation="Insufficient repository context.",
        kind="must_refuse",
    ),
    EvalCase(
        id=15,
        section="Negative tests",
        question="Trace foo_bar_baz to quantum_entry_gate.",
        expectation="Insufficient repository context.",
        kind="must_refuse",
    ),
    EvalCase(
        id=16,
        section="Negative tests",
        question="Explain the Kubernetes deployment for this repo.",
        expectation="Refusal unless repo actually contains that context.",
        kind="must_refuse_or_grounded",
        expected_sources=("kubernetes", "helm", "deploy", "README.md", "docs/"),
    ),
    EvalCase(
        id=17,
        section="Source quality",
        question="Explain the operator workflow.",
        expectation="Do not widen into weak extras when docs/OPERATOR.md is enough.",
        kind="docs_strong_source",
        expected_sources=("docs/OPERATOR.md",),
        forbidden_phrases=("README", "HANDOFF"),
    ),
    EvalCase(
        id=18,
        section="Source quality",
        question="Trace fetch_market_data to broker.open_position.",
        expectation="No noisy or repetitive source list.",
        kind="trace_safe",
        expected_sources=("files/data/market.py", "files/broker/"),
    ),
    EvalCase(
        id=19,
        section="Source quality",
        question="Where is GuardedBroker defined?",
        expectation="Do not answer one file and cite another.",
        kind="definition_exact",
        expected_sources=("files/broker/guarded.py",),
        expected_phrases=("files/broker/guarded.py",),
    ),
    EvalCase(
        id=20,
        section="Source quality",
        question="What is this repo?",
        expectation="Grounded repo summary, not generic filler.",
        kind="docs_grounded",
        expected_sources=("rag/README.md", "README.md", "docs/", "HANDOFF"),
        forbidden_phrases=("Kubernetes", "Terraform", "service mesh"),
    ),
]


def _run_question(question: str) -> str:
    if not RAG_SH.exists():
        raise FileNotFoundError(f"Missing script: {RAG_SH}")

    result = subprocess.run(
        [str(RAG_SH), question],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"rag.sh failed for question {question!r}: {detail}")

    return (result.stdout or "").strip()


def _extract_sources(answer: str) -> list[str]:
    if "Sources:" not in answer:
        return []

    _, tail = answer.split("Sources:", 1)
    out: list[str] = []

    for raw in tail.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            out.append(line[2:].strip())
            continue
        out.append(line)

    return out


def _answer_text(answer: str) -> str:
    if "Sources:" in answer:
        head, _ = answer.split("Sources:", 1)
        return head.strip()
    return answer.strip()


def _has_refusal(answer: str) -> bool:
    return "Insufficient repository context." in answer


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    text_l = text.lower()
    return any(n.lower() in text_l for n in needles)


def _sources_contain_any(sources: list[str], needles: tuple[str, ...]) -> bool:
    if not needles:
        return True
    joined = "\n".join(sources).lower()
    return any(n.lower() in joined for n in needles)


def _sources_have_duplicates(sources: list[str]) -> bool:
    seen: set[str] = set()
    for src in sources:
        if src in seen:
            return True
        seen.add(src)
    return False


def _definition_answer_matches_expected(answer: str, expected_sources: tuple[str, ...]) -> bool:
    text = answer.lower()
    return any(src.lower() in text for src in expected_sources)


def _evaluate_case(case: EvalCase, answer: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    sources = _extract_sources(answer)
    answer_text = _answer_text(answer)

    if not sources:
        notes.append("missing sources")
    if _sources_have_duplicates(sources):
        notes.append("duplicate sources")

    if case.forbidden_phrases and _contains_any(answer, case.forbidden_phrases):
        notes.append("contains forbidden phrase/source")

    if case.kind == "must_refuse":
        if _has_refusal(answer):
            return "PASS", notes
        notes.append("should refuse")
        return "FAIL", notes

    if case.kind == "must_refuse_or_grounded":
        if _has_refusal(answer):
            return "PASS", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("non-refusal answer lacks relevant sources")
            return "FAIL", notes
        return "PASS", notes

    if case.kind == "definition_exact":
        if _has_refusal(answer):
            notes.append("refused exact definition")
            return "FAIL", notes
        if not _definition_answer_matches_expected(answer, case.expected_sources):
            notes.append("answer missing expected definition path")
            return "FAIL", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("sources missing expected definition path")
            return "FAIL", notes
        if case.expected_phrases and not _contains_any(answer, case.expected_phrases):
            notes.append("answer missing expected exact phrase")
            return "FAIL", notes
        return "PASS", notes

    if case.kind == "definition_flexible":
        if _has_refusal(answer):
            return "REVIEW", notes + ["refused flexible definition question"]
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("sources do not look relevant")
            return "FAIL", notes
        return "PASS", notes

    if case.kind == "definition_or_refusal":
        if _has_refusal(answer):
            return "PASS", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("non-refusal answer lacks plausible repo source")
            return "FAIL", notes
        return "REVIEW", notes + ["needs human check for exactness"]

    if case.kind == "trace_safe":
        if _has_refusal(answer):
            if case.expected_sources and not _sources_contain_any(sources, case.expected_sources):
                notes.append("refusal sources do not look relevant")
                return "REVIEW", notes
            return "PASS", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("trace answer lacks relevant sources")
            return "FAIL", notes
        generic_markers = (
            "typically",
            "usually",
            "probably",
            "likely",
            "generally",
            "common pattern",
        )
        if _contains_any(answer_text, generic_markers):
            notes.append("trace answer sounds inferential")
            return "FAIL", notes
        return "REVIEW", notes + ["grounded trace needs human verification"]

    if case.kind == "docs_grounded":
        if _has_refusal(answer):
            notes.append("refused docs question")
            return "FAIL", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("docs answer missing plausible doc sources")
            return "FAIL", notes
        return "PASS", notes

    if case.kind == "docs_grounded_or_refusal":
        if _has_refusal(answer):
            if _sources_contain_any(sources, case.expected_sources):
                return "REVIEW", notes + ["refused despite plausible doc source"]
            return "PASS", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("docs answer missing plausible doc sources")
            return "FAIL", notes
        return "PASS", notes

    if case.kind == "docs_strong_source":
        if _has_refusal(answer):
            notes.append("refused docs question")
            return "FAIL", notes
        if not _sources_contain_any(sources, case.expected_sources):
            notes.append("topical doc source missing")
            return "FAIL", notes
        bad_sources = [s for s in sources if "readme" in s.lower() or "handoff" in s.lower()]
        if bad_sources and "docs/operator.md".lower() in case.expected_sources[0].lower():
            notes.append("source widening beyond strongest doc")
            return "FAIL", notes
        return "PASS", notes

    notes.append("unknown eval kind")
    return "REVIEW", notes


def _markdown_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _write_report(
    out_dir: Path,
    commit: str,
    results: list[dict],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = out_dir / f"eval_{ts}.md"
    json_path = out_dir / f"eval_{ts}.json"

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    review_count = sum(1 for r in results if r["status"] == "REVIEW")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    lines: list[str] = []
    lines.append(f"# RAG Eval Run — {ts}")
    lines.append("")
    lines.append(f"- Commit: `{commit}`")
    lines.append(f"- Cases: `{len(results)}`")
    lines.append(f"- PASS: `{pass_count}`")
    lines.append(f"- REVIEW: `{review_count}`")
    lines.append(f"- FAIL: `{fail_count}`")
    lines.append("")
    lines.append("| ID | Section | Status | Question | Notes |")
    lines.append("|---:|---|---|---|---|")

    for r in results:
        notes = "; ".join(r["notes"]) if r["notes"] else ""
        lines.append(
            f"| {r['id']} | {_markdown_escape(r['section'])} | {r['status']} | "
            f"{_markdown_escape(r['question'])} | {_markdown_escape(notes)} |"
        )

    lines.append("")
    lines.append("## Detailed results")
    lines.append("")

    for r in results:
        lines.append(f"### Q{r['id']} — {r['status']}")
        lines.append("")
        lines.append(f"**Section:** {r['section']}")
        lines.append("")
        lines.append(f"**Question:** `{r['question']}`")
        lines.append("")
        lines.append(f"**Expectation:** {r['expectation']}")
        lines.append("")
        if r["notes"]:
            lines.append("**Notes:**")
            lines.append("")
            for note in r["notes"]:
                lines.append(f"- {note}")
            lines.append("")
        lines.append("**Answer:**")
        lines.append("")
        lines.append("```text")
        lines.append(r["answer"].rstrip())
        lines.append("```")
        lines.append("")

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return md_path


def run_eval(limit: int | None = None) -> Path:
    commit = _git_commit(REPO_ROOT)
    selected = EVAL_CASES[:limit] if limit and limit > 0 else EVAL_CASES
    results: list[dict] = []

    for case in selected:
        answer = _run_question(case.question)
        status, notes = _evaluate_case(case, answer)
        results.append(
            {
                "id": case.id,
                "section": case.section,
                "question": case.question,
                "expectation": case.expectation,
                "kind": case.kind,
                "status": status,
                "notes": notes,
                "answer": answer,
            }
        )
        print(f"Q{case.id:02d} {status} — {case.question}")

    report_path = _write_report(HERE / "eval_runs", commit, results)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    review_count = sum(1 for r in results if r["status"] == "REVIEW")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    print()
    print(f"Report: {report_path}")
    print(f"PASS={pass_count} REVIEW={review_count} FAIL={fail_count}")

    return report_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    run_eval(limit=args.limit or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
