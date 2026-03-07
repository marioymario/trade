#!/usr/bin/env python3

# rag/query.py
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from pathlib import Path

import ollama
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

DB_PATH = "/vector_db"
REPO_PATH = "/repo"
MODEL = os.environ.get("RAG_MODEL", "qwen2.5-coder:14b")
TOP_K = int(os.environ.get("RAG_TOP_K", "6"))
FETCH_K = int(os.environ.get("RAG_FETCH_K", "18"))

CODE_EXT = {".py", ".sh", ".yml", ".yaml"}
DOC_EXT = {".md", ".txt"}
ALL_EXT = CODE_EXT | DOC_EXT

SKIP_PATH_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "vector_db",
    "rag-cache",
    "eval_runs",
}

SKIP_PREFIXES = (
    "rag/eval_runs/",
    "vector_db/",
    "rag-cache/",
)

SKIP_SUBSTRINGS = (
    "/eval_runs/",
    "/vector_db/",
    "/rag-cache/",
)

WEAK_DOC_SOURCE_PATTERNS = (
    "eval_set",
    "eval-run",
    "eval_run",
    "eval runner",
    "eval_runner",
    "eval_runs",
)


def _quiet_embedding() -> HuggingFaceEmbeddings:
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )


def build_db() -> Chroma:
    embedding = _quiet_embedding()
    return Chroma(
        persist_directory=DB_PATH,
        embedding_function=embedding,
    )


def _query_terms(query: str) -> list[str]:
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*", query)
    terms: list[str] = []
    seen: set[str] = set()

    for term in raw:
        t = term.strip().lower()
        if len(t) < 2:
            continue
        if t in seen:
            continue
        seen.add(t)
        terms.append(t)

    return terms


def _symbol_terms(query: str) -> list[str]:
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
    skip = {
        "trace",
        "explain",
        "where",
        "what",
        "does",
        "from",
        "to",
        "the",
        "this",
        "that",
        "workflow",
        "operator",
        "repo",
        "system",
        "code",
        "file",
        "path",
        "call",
        "show",
        "question",
        "defined",
        "definition",
        "help",
        "is",
        "are",
        "how",
    }

    out: list[str] = []
    seen: set[str] = set()

    for item in raw:
        if len(item) < 3:
            continue
        if item.lower() in skip:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)

    return out


def _detect_mode(query: str) -> str:
    q = query.lower().strip()

    trace_markers = [
        "trace ",
        "path ",
        "flow ",
        "how does ",
        "where does ",
        "what calls ",
        "call chain",
        "reach ",
    ]
    code_markers = [
        "function ",
        "method ",
        "class ",
        "where is ",
        "show me ",
        "defined",
        "definition",
        "python -m",
        "decisions.csv",
    ]
    doc_markers = [
        "overview",
        "architecture",
        "operator",
        "workflow",
        "handoff",
        "readme",
        "how does this system work",
        "what is this repo",
        "design intent",
        "what is the rag for",
        "what is this rag for",
    ]

    if any(m in q for m in trace_markers):
        return "trace"
    if any(m in q for m in code_markers):
        return "code"
    if any(m in q for m in doc_markers):
        return "docs"

    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\(", query):
        return "code"
    if "." in query or "_" in query:
        return "code"

    return "mixed"


def _looks_like_weak_doc_source(source: str) -> bool:
    source_l = source.lower()
    return any(pat in source_l for pat in WEAK_DOC_SOURCE_PATTERNS)


def _file_type_boost(source: str, mode: str) -> int:
    p = Path(source.lower())
    ext = p.suffix

    if mode in {"code", "trace"}:
        if ext in CODE_EXT:
            return 12
        if ext in DOC_EXT:
            return 2
        return 0

    if mode == "docs":
        if ext in DOC_EXT:
            return 12
        if ext in CODE_EXT:
            return 2
        return 0

    if ext in CODE_EXT:
        return 6
    if ext in DOC_EXT:
        return 6
    return 0


def _kind_boost(kind: str, mode: str) -> int:
    kind = (kind or "").lower()

    if mode == "trace":
        if kind == "function":
            return 14
        if kind == "class":
            return 10
        if kind == "module":
            return 6
        return 2

    if mode == "code":
        if kind == "function":
            return 12
        if kind == "class":
            return 10
        if kind == "module":
            return 6
        return 2

    if mode == "docs":
        if kind == "file":
            return 8
        return 2

    if kind in {"function", "class", "module"}:
        return 6
    return 4


def _query_path_hints(query: str) -> set[str]:
    q = query.lower()
    hints: set[str] = set()

    mapping = {
        "broker": ["broker", "open_position", "paperbroker", "guardedbroker", "close_position"],
        "market": ["fetch_market_data", "market", "ohlcv"],
        "features": ["validate_latest_features", "compute_features", "features", "atr", "ema", "rsi"],
        "main": ["main", "entry", "decision", "decisions.csv", "loop"],
        "ops": ["operator", "workflow", "handoff", "readme", "deploy", "rag"],
    }

    for hint, markers in mapping.items():
        if any(marker in q for marker in markers):
            hints.add(hint)

    return hints


def _path_family_boost(source: str, mode: str, query: str) -> int:
    source_l = source.lower()
    hints = _query_path_hints(query)
    score = 0

    if "broker" in hints and "/broker/" in source_l:
        score += 14
    if "market" in hints and "/data/" in source_l:
        score += 10
    if "features" in hints and "/data/" in source_l:
        score += 12
    if "main" in hints and source_l == "files/main.py":
        score += 16
    if "ops" in hints and (
        source_l.startswith("docs/")
        or "handoff" in source_l
        or source_l.endswith("readme.md")
    ):
        score += 12

    if mode == "trace":
        if "/backtest/" in source_l:
            score -= 18
        if "test" in source_l:
            score -= 14
        if "smoke" in source_l:
            score -= 10

    if mode in {"code", "trace"} and source_l.endswith("__init__.py"):
        score -= 6

    return score


def _docs_source_boost(source: str, query: str) -> int:
    source_l = source.lower()
    q = query.lower()
    score = 0

    if _looks_like_weak_doc_source(source_l):
        score -= 40

    if "operator" in q or "workflow" in q:
        if source_l == "docs/operator.md":
            score += 40
        elif source_l.startswith("docs/"):
            score += 14
        elif "handoff" in source_l or "readme" in source_l:
            score -= 4

    if "handoff" in q or "rag is for" in q or "rag for" in q:
        if "handoff" in source_l:
            score += 34
        elif source_l == "rag/readme.md":
            score += 20
        elif source_l.endswith("readme.md"):
            score += 10
        elif source_l.startswith("docs/"):
            score += 8

    if "readme" in q or "what is this repo" in q:
        if source_l == "rag/readme.md":
            score += 34
        elif source_l.endswith("readme.md"):
            score += 24

    if "deploy" in q or "use rhythm" in q:
        if source_l == "rag/readme.md":
            score += 22
        elif "handoff" in source_l:
            score += 16

    return score


def _score_doc(
    query: str,
    query_terms: list[str],
    source: str,
    content: str,
    metadata: dict,
    mode: str,
) -> int:
    score = _file_type_boost(source, mode)
    score += _kind_boost(metadata.get("kind", ""), mode)
    score += _path_family_boost(source, mode, query)

    source_l = source.lower()
    content_l = content.lower()
    symbol = str(metadata.get("symbol", "")).strip()
    symbol_l = symbol.lower()
    imports_l = str(metadata.get("imports", "")).lower()
    module_stem = str(metadata.get("module_stem", "")).lower()
    calls_l = str(metadata.get("calls", "")).lower()
    attr_calls_l = str(metadata.get("attr_calls", "")).lower()
    methods_l = str(metadata.get("methods", "")).lower()

    if mode == "docs":
        score += _docs_source_boost(source, query)
        if _looks_like_weak_doc_source(source):
            score -= 30

    for term in query_terms:
        if term in source_l:
            score += 10

        hits = content_l.count(term)
        if hits > 0:
            score += min(hits, 8) * 4

        if term == symbol_l and symbol_l:
            score += 22
        elif symbol_l and term in symbol_l:
            score += 8

        if term == module_stem and module_stem:
            score += 12

        if term in imports_l:
            score += 4
        if term in calls_l:
            score += 6
        if term in attr_calls_l:
            score += 8
        if term in methods_l:
            score += 4

    for sym in _symbol_terms(query):
        sym_l = sym.lower()
        if sym_l == symbol_l and symbol_l:
            score += 30
        elif symbol_l and sym_l in symbol_l:
            score += 10

        if sym_l == module_stem and module_stem:
            score += 14

        if re.search(rf"\b{re.escape(sym_l)}\b", content_l):
            score += 8

        if sym_l in calls_l:
            score += 8
        if sym_l in attr_calls_l:
            score += 10
        if sym_l in methods_l:
            score += 5

    if mode in {"code", "trace"} and "files/main.py" in source_l:
        score += 3

    if mode == "docs" and (
        source_l.startswith("docs/")
        or "handoff" in source_l
        or "readme" in source_l
    ):
        score += 4

    if mode == "trace" and ("def " in content_l or "class " in content_l):
        score += 3

    if mode == "trace":
        if calls_l or attr_calls_l:
            score += 4
        if "decisions.csv" in query.lower() and "decisions.csv" in content_l:
            score += 20
        if "open_position" in query.lower() and "open_position" in attr_calls_l:
            score += 16
        if "open_position" in query.lower() and "open_position" in calls_l:
            score += 12

    if metadata.get("exact_definition") is True:
        score += 20
    elif metadata.get("exact_reference") is True:
        score -= 4

    return score


def _rerank_docs(query: str, docs: list, mode: str) -> list:
    query_terms = _query_terms(query)
    scored = []

    for d in docs:
        source = d.metadata.get("source", "unknown")
        score = _score_doc(query, query_terms, source, d.page_content, d.metadata, mode)
        scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]


def _dedupe_and_trim(docs: list, limit: int) -> list:
    seen = set()
    out = []

    for d in docs:
        source = d.metadata.get("source", "unknown")
        kind = d.metadata.get("kind", "")
        symbol = d.metadata.get("symbol", "")
        content = d.page_content.strip()
        key = (source, kind, symbol, content[:240])

        if key in seen:
            continue

        seen.add(key)
        out.append(d)

        if len(out) >= limit:
            break

    return out


def _read_text_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _allow_source_by_mode(rel_path: str, mode: str) -> bool:
    ext = Path(rel_path).suffix.lower()

    if ext not in ALL_EXT:
        return False

    if mode in {"code", "trace"}:
        return ext in CODE_EXT
    if mode == "docs":
        return ext in DOC_EXT
    return ext in ALL_EXT


def _should_skip_rel_path(rel_path: str) -> bool:
    rel_posix = Path(rel_path).as_posix()

    parts = set(Path(rel_posix).parts)
    if parts & SKIP_PATH_PARTS:
        return True

    if any(rel_posix.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True

    if any(token in rel_posix for token in SKIP_SUBSTRINGS):
        return True

    return False


def _snippet_around_matches(text: str, query_terms: list[str]) -> str:
    lines = text.splitlines()
    blocks = []

    for idx, line in enumerate(lines):
        line_l = line.lower()
        if any(term in line_l for term in query_terms):
            start = max(0, idx - 3)
            end = min(len(lines), idx + 4)
            block = "\n".join(lines[start:end])
            blocks.append(block)
            if len(blocks) >= 3:
                break

    if blocks:
        return "\n\n".join(blocks)

    return text[:1200]


def _definition_type(text_l: str, sym_l: str) -> str | None:
    if re.search(rf"^\s*class\s+{re.escape(sym_l)}\b", text_l, re.MULTILINE):
        return "class"
    if re.search(rf"^\s*(async\s+def|def)\s+{re.escape(sym_l)}\b", text_l, re.MULTILINE):
        return "function"
    return None


def _exact_match_docs(query: str, mode: str) -> list:
    repo = Path(REPO_PATH)
    symbols = _symbol_terms(query)
    if not symbols:
        return []

    matches = []

    for path in repo.rglob("*"):
        if not path.is_file():
            continue

        rel_path = path.relative_to(repo).as_posix()
        if _should_skip_rel_path(rel_path):
            continue
        if not _allow_source_by_mode(rel_path, mode):
            continue
        if mode == "docs" and _looks_like_weak_doc_source(rel_path):
            continue

        text = _read_text_file(path)
        if not text:
            continue

        lines = text.splitlines()
        text_l = text.lower()

        for sym in symbols:
            sym_l = sym.lower()
            score = 0
            blocks = []
            definition_found = False

            for idx, line in enumerate(lines):
                line_l = line.lower()

                if re.search(rf"^\s*class\s+{re.escape(sym_l)}\b", line_l):
                    score += 120
                    definition_found = True
                elif re.search(rf"^\s*(async\s+def|def)\s+{re.escape(sym_l)}\b", line_l):
                    score += 120
                    definition_found = True
                elif re.search(rf"\b{re.escape(sym_l)}\b", line_l):
                    score += 12
                else:
                    continue

                start = max(0, idx - 3)
                end = min(len(lines), idx + 8)
                blocks.append("\n".join(lines[start:end]))

                if len(blocks) >= 3:
                    break

            if score <= 0:
                continue

            kind = _definition_type(text_l, sym_l) or "file"

            metadata = {
                "source": rel_path,
                "kind": kind,
                "symbol": sym if definition_found else "",
                "parent": "",
                "imports": "",
                "module_stem": Path(rel_path).stem,
                "calls": "",
                "attr_calls": "",
                "methods": "",
                "exact_definition": definition_found,
                "exact_reference": not definition_found,
            }

            snippet = "\n\n".join(blocks) if blocks else text[:1200]
            doc = type(
                "Doc",
                (),
                {
                    "page_content": f"FILE: {rel_path}\nKIND: {kind}\n"
                    + (f"SYMBOL: {sym}\n" if definition_found else "")
                    + f"\n{snippet}",
                    "metadata": metadata,
                },
            )()
            matches.append((score, doc))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in matches[: max(TOP_K, 8)]]


def _grep_fallback_docs(query: str, mode: str) -> list:
    query_terms = _query_terms(query)
    symbols = _symbol_terms(query)
    repo = Path(REPO_PATH)
    matches = []

    for path in repo.rglob("*"):
        if not path.is_file():
            continue

        rel_path = path.relative_to(repo).as_posix()
        if _should_skip_rel_path(rel_path):
            continue
        if not _allow_source_by_mode(rel_path, mode):
            continue
        if mode == "docs" and _looks_like_weak_doc_source(rel_path):
            continue

        text = _read_text_file(path)
        if not text:
            continue

        text_l = text.lower()
        source_hits = 0
        content_hits = 0
        symbol_hits = 0
        has_definition = False

        for term in query_terms:
            if term in rel_path.lower():
                source_hits += 1
            content_hits += text_l.count(term)

        for sym in symbols:
            sym_l = sym.lower()
            if re.search(rf"^\s*(async\s+def|def)\s+{re.escape(sym_l)}\b", text_l, re.MULTILINE):
                symbol_hits += 8
                has_definition = True
            if re.search(rf"^\s*class\s+{re.escape(sym_l)}\b", text_l, re.MULTILINE):
                symbol_hits += 8
                has_definition = True
            if re.search(rf"\b{re.escape(sym_l)}\b", text_l):
                symbol_hits += 1

        base_score = _file_type_boost(rel_path, mode) + _path_family_boost(rel_path, mode, query)
        if mode == "docs":
            base_score += _docs_source_boost(rel_path, query)

        total_score = base_score + source_hits * 10 + min(content_hits, 12) * 3 + symbol_hits * 10

        if total_score <= 0:
            continue

        snippet = _snippet_around_matches(text, query_terms + [s.lower() for s in symbols])
        metadata = {
            "source": rel_path,
            "kind": "file",
            "symbol": "",
            "parent": "",
            "imports": "",
            "module_stem": Path(rel_path).stem,
            "calls": "",
            "attr_calls": "",
            "methods": "",
            "exact_definition": has_definition,
            "exact_reference": not has_definition,
        }

        doc = type(
            "Doc",
            (),
            {"page_content": f"FILE: {rel_path}\n\n{snippet}", "metadata": metadata},
        )()
        matches.append((total_score, doc))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in matches[:TOP_K]]


def _collect_docs(db: Chroma, query: str) -> tuple[list, str]:
    mode = _detect_mode(query)
    query_terms = _query_terms(query)
    symbols = _symbol_terms(query)

    docs = []

    if mode in {"code", "trace"}:
        docs.extend(_exact_match_docs(query, mode))

    docs.extend(db.similarity_search(query, k=FETCH_K))

    for term in query_terms[:8]:
        docs.extend(db.similarity_search(term, k=4))

    for sym in symbols[:8]:
        docs.extend(db.similarity_search(sym, k=6))
        docs.extend(db.similarity_search(f"symbol {sym}", k=4))
        docs.extend(db.similarity_search(f"function {sym}", k=4))
        docs.extend(db.similarity_search(f"class {sym}", k=4))
        docs.extend(db.similarity_search(f"calls {sym}", k=4))
        docs.extend(db.similarity_search(f"attr_calls {sym}", k=4))

    docs.extend(_grep_fallback_docs(query, mode))

    reranked = _rerank_docs(query, docs, mode)

    if mode == "docs":
        reranked = [
            d for d in reranked
            if Path(d.metadata.get("source", "")).suffix.lower() in DOC_EXT
            and not _looks_like_weak_doc_source(d.metadata.get("source", ""))
        ]

    return _dedupe_and_trim(reranked, TOP_K), mode


def _definition_question(query: str) -> bool:
    q = query.lower()
    markers = [
        "where is ",
        "where are ",
        "defined",
        "definition",
        "what file defines",
        "which file defines",
    ]
    return any(m in q for m in markers)


def _trace_question(query: str, mode: str) -> bool:
    if mode == "trace":
        return True
    q = query.lower()
    return any(
        m in q
        for m in [
            "trace ",
            "path ",
            "flow ",
            "how does ",
            "where does ",
            "what calls ",
            "call chain",
            "reach ",
        ]
    )


def _definition_docs(docs: list) -> list:
    out = []
    for d in docs:
        if d.metadata.get("exact_definition") is True:
            out.append(d)
    return out


def _display_source_line(d) -> str:
    source = d.metadata.get("source", "unknown")
    kind = d.metadata.get("kind", "")
    symbol = d.metadata.get("symbol", "")

    if kind in {"class", "function"} and symbol:
        return f"{source} ({kind}: {symbol})"
    if kind == "module":
        return f"{source} (module)"
    return source


def _canonical_source_key(d) -> tuple[str, str]:
    source = d.metadata.get("source", "unknown")
    symbol = str(d.metadata.get("symbol", "")).strip()
    kind = str(d.metadata.get("kind", "")).strip()

    if kind in {"class", "function"} and symbol:
        return source, symbol

    return source, ""


def _dedupe_source_docs(docs: list) -> list:
    out = []
    seen: set[tuple[str, str]] = set()

    for d in docs:
        key = _canonical_source_key(d)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)

    return out


def _source_list_lines(docs: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for d in _dedupe_source_docs(docs):
        line = _display_source_line(d)
        if line in seen:
            continue
        seen.add(line)
        out.append(f"- {line}")

    return out


def _filter_refusal_docs(query: str, docs: list, mode: str) -> list:
    q = query.lower()
    filtered = []

    for d in docs:
        source = str(d.metadata.get("source", ""))
        source_l = source.lower()
        content_l = d.page_content.lower()

        if mode == "docs" and _looks_like_weak_doc_source(source):
            continue

        if "handoff" in q:
            if "handoff" in source_l or source_l == "rag/readme.md" or source_l.endswith("readme.md"):
                filtered.append(d)
                continue

        if "decisions.csv" in q:
            if "decisions.csv" in content_l or source_l in {"files/main.py", "files/data/decisions.py"}:
                filtered.append(d)
                continue

        filtered.append(d)

    return filtered or docs


def _trace_source_list_lines(query: str, docs: list) -> list[str]:
    docs = _filter_refusal_docs(query, docs, "trace")
    symbols = _symbol_terms(query)
    if not symbols:
        return _source_list_lines(docs)

    out: list[str] = []
    seen_lines: set[str] = set()

    for sym in symbols:
        sym_l = sym.lower()
        for d in docs:
            doc_sym = str(d.metadata.get("symbol", "")).strip().lower()
            content_l = d.page_content.lower()
            calls_l = str(d.metadata.get("calls", "")).lower()
            attr_calls_l = str(d.metadata.get("attr_calls", "")).lower()

            if not (
                doc_sym == sym_l
                or sym_l in content_l
                or sym_l in calls_l
                or sym_l in attr_calls_l
            ):
                continue

            line = _display_source_line(d)
            if line in seen_lines:
                break

            seen_lines.add(line)
            out.append(f"- {line}")
            break

    if out:
        return out

    return _source_list_lines(docs)


def _definition_paths(docs: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for d in docs:
        source = d.metadata.get("source", "unknown")
        if source in seen:
            continue
        seen.add(source)
        out.append(source)

    return out


def _sufficient_for_definition(query: str, docs: list) -> bool:
    symbols = _symbol_terms(query)
    defs = _definition_docs(docs)
    if not symbols or not defs:
        return False

    for sym in symbols:
        sym_l = sym.lower()
        for d in defs:
            doc_sym = str(d.metadata.get("symbol", "")).lower()
            content_l = d.page_content.lower()
            if doc_sym == sym_l:
                return True
            if re.search(rf"^\s*symbol:\s*{re.escape(sym_l)}\s*$", content_l, re.MULTILINE):
                return True

    return False


def _caller_docs_for_target(query: str, docs: list) -> tuple[list, str] | None:
    q = query.lower()
    if "what calls " not in q:
        return None

    symbols = _symbol_terms(query)
    if not symbols:
        return None

    target = symbols[-1].lower()
    callers = []

    for d in docs:
        if str(d.metadata.get("kind", "")).lower() != "function":
            continue
        symbol = str(d.metadata.get("symbol", "")).strip()
        symbol_l = symbol.lower()
        if symbol_l == target:
            continue

        calls_l = str(d.metadata.get("calls", "")).lower()
        attr_calls_l = str(d.metadata.get("attr_calls", "")).lower()

        if target in calls_l or target in attr_calls_l:
            callers.append(d)

    callers = _dedupe_source_docs(callers)
    if not callers:
        return None

    return callers[:3], target


def _decisions_trace_docs(query: str, docs: list) -> list:
    if "decisions.csv" not in query.lower():
        return []

    out = []
    for d in docs:
        source = str(d.metadata.get("source", "")).lower()
        content_l = d.page_content.lower()
        calls_l = str(d.metadata.get("calls", "")).lower()
        attr_calls_l = str(d.metadata.get("attr_calls", "")).lower()

        if (
            source in {"files/main.py", "files/data/decisions.py"}
            or "decisions.csv" in content_l
            or "append_decision_csv" in content_l
            or "append_decision_csv" in calls_l
            or "append_decision_csv" in attr_calls_l
        ):
            out.append(d)

    return _dedupe_source_docs(out)


def _try_grounded_trace_answer(query: str, docs: list, mode: str) -> str | None:
    if not _trace_question(query, mode):
        return None

    caller_match = _caller_docs_for_target(query, docs)
    if caller_match is not None:
        caller_docs, target = caller_match
        source_lines = _source_list_lines(caller_docs)
        caller_names = []

        for d in caller_docs:
            symbol = str(d.metadata.get("symbol", "")).strip()
            source = str(d.metadata.get("source", "")).strip()
            if symbol and source:
                caller_names.append(f"`{symbol}` in `{source}`")

        if caller_names:
            joined = "; ".join(caller_names[:3])
            return (
                f"Answer:\nRetrieved caller evidence points to {joined} calling `{target}`, "
                "but a complete grounded call-chain beyond that is not established.\n\n"
                "Sources:\n" + "\n".join(source_lines)
            )

    decisions_docs = _decisions_trace_docs(query, docs)
    if decisions_docs:
        source_lines = _source_list_lines(decisions_docs)
        main_present = any(str(d.metadata.get("source", "")).lower() == "files/main.py" for d in decisions_docs)
        decisions_present = any(str(d.metadata.get("source", "")).lower() == "files/data/decisions.py" for d in decisions_docs)

        if main_present and decisions_present:
            return (
                "Answer:\nRetrieved context supports a partial path: decision generation is anchored in "
                "`files/main.py`, and CSV writing is anchored in `files/data/decisions.py` via decision-append logic. "
                "A fuller end-to-end path is not stated beyond those grounded anchors.\n\n"
                "Sources:\n" + "\n".join(source_lines)
            )

    return None


def _sufficient_for_trace(query: str, docs: list) -> bool:
    grounded = _try_grounded_trace_answer(query, docs, "trace")
    if grounded is not None:
        return True

    symbols = _symbol_terms(query)
    if len(symbols) < 2:
        return False

    defs = _definition_docs(docs)
    if len(defs) < 2:
        return False

    hits = 0
    for sym in symbols[:2]:
        sym_l = sym.lower()
        for d in defs:
            doc_sym = str(d.metadata.get("symbol", "")).lower()
            if doc_sym == sym_l:
                hits += 1
                break

    return hits >= 2


def _guarded_response(query: str, docs: list, mode: str) -> str | None:
    if _trace_question(query, mode):
        grounded = _try_grounded_trace_answer(query, docs, mode)
        if grounded is not None:
            return grounded

        if not _sufficient_for_trace(query, docs):
            lines = _trace_source_list_lines(query, docs)
            return "Answer:\nInsufficient repository context.\n\nSources:\n" + "\n".join(lines)

    if _definition_question(query):
        defs = _definition_docs(docs)

        if not _sufficient_for_definition(query, docs):
            lines = _source_list_lines(docs)
            return "Answer:\nInsufficient repository context.\n\nSources:\n" + "\n".join(lines)

        paths = _definition_paths(defs)
        if not paths:
            lines = _source_list_lines(docs)
            return "Answer:\nInsufficient repository context.\n\nSources:\n" + "\n".join(lines)

        if len(paths) == 1:
            return f"Answer:\nDefined in `{paths[0]}`.\n\nSources:\n- {paths[0]}"

        lines = "\n".join(f"- {p}" for p in paths)
        return f"Answer:\nMultiple definition candidates found.\n\nSources:\n{lines}"

    return None


def _docs_guarded_response(query: str, docs: list, mode: str) -> str | None:
    if mode != "docs":
        return None

    docs = _filter_refusal_docs(query, docs, "docs")

    if not docs:
        return "Answer:\nInsufficient repository context.\n\nSources:\n"

    q = query.lower()
    top = docs[0]
    top_source = top.metadata.get("source", "unknown").lower()

    if ("operator" in q or "workflow" in q) and top_source == "docs/operator.md":
        return None

    if "handoff" in q and ("handoff" in top_source or top_source == "rag/readme.md"):
        return None

    if "what is this repo" in q and top_source.endswith("readme.md"):
        return None

    if ("deploy" in q or "use rhythm" in q) and top_source.endswith("readme.md"):
        return None

    return None


def answer_question(db: Chroma, query: str) -> str:
    docs, mode = _collect_docs(db, query)

    guarded = _guarded_response(query, docs, mode)
    if guarded is not None:
        return guarded

    docs_guarded = _docs_guarded_response(query, docs, mode)
    if docs_guarded is not None:
        return docs_guarded

    context_docs = docs
    if mode == "docs" and docs:
        primary = docs[0].metadata.get("source", "")
        context_docs = [d for d in docs if d.metadata.get("source", "") == primary] or docs[:1]

    context_docs = _dedupe_source_docs(context_docs)

    context_parts = []

    for i, d in enumerate(context_docs, start=1):
        label = _display_source_line(d)
        context_parts.append(f"[{i}] SOURCE: {label}\n{d.page_content}")

    context = "\n\n".join(context_parts)
    sources_block = "\n".join(_source_list_lines(context_docs))

    prompt = f"""You are a repository-aware software engineering assistant.

Rules:
- Answer only from the provided repository context.
- Do not infer missing code paths from typical patterns.
- If the context is insufficient, say exactly: "Insufficient repository context."
- Be concrete and practical.
- Mention file paths only if they appear in the provided context.
- Prefer short, grounded answers.
- If tracing a path, only name steps explicitly supported by the retrieved context.
- Keep the Sources section short and deduplicated.
- For docs questions, prefer the strongest matching doc source and do not invent source labels.
- If you refuse, the Sources section must still list only actual repository file paths from the provided context.
- Retrieval mode for this question is: {mode}

Response format:
Answer:
<grounded answer>

Sources:
<one source path per line>

Repository context:
{context}

Question:
{query}
"""

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response["message"]["content"].strip()

    if "Sources:" not in content:
        content = f"{content}\n\nSources:\n{sources_block}"

    return content


def repl() -> int:
    print(f"Repo assistant ready. model={MODEL}")
    print("Type a question. Commands: :quit  :exit  :help")

    db = build_db()

    while True:
        try:
            query = input("\nrag> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not query:
            continue

        if query in {":quit", ":exit"}:
            return 0

        if query == ":help":
            print("Ask questions about the repo.")
            print("Examples:")
            print("  Where is degraded mode triggered?")
            print("  What blocks entries besides ARM?")
            print("  Trace fetch_market_data to broker.open_position.")
            print("  Explain the operator workflow.")
            continue

        try:
            answer = answer_question(db, query)
            print()
            print(answer)
        except KeyboardInterrupt:
            print("\nInterrupted.")
        except Exception as e:
            print(f"\nERROR: {e}")


def oneshot(argv: list[str]) -> int:
    if len(argv) < 2:
        return repl()

    query = " ".join(argv[1:]).strip()
    if not query:
        return repl()

    db = build_db()
    try:
        print(answer_question(db, query))
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(oneshot(sys.argv))
