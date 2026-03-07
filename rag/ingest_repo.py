#!/usr/bin/env python3

import ast
import contextlib
import io
import os
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

REPO_PATH = "/repo"
DB_PATH = "/vector_db"

ALLOWED_EXT = {
    ".py",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".sh",
}

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "vector_db",
    "rag-cache",
    "eval_runs",
}

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

SKIP_FILE_NAMES = {
    ".DS_Store",
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


def _quiet_embedding() -> HuggingFaceEmbeddings:
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _base_metadata(rel_path: str, ext: str) -> dict:
    language = {
        ".py": "python",
        ".md": "markdown",
        ".txt": "text",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".sh": "shell",
    }.get(ext, "text")

    return {
        "source": rel_path,
        "language": language,
        "kind": "file",
        "symbol": "",
        "parent": "",
        "imports": "",
        "module_stem": Path(rel_path).stem,
        "calls": "",
        "attr_calls": "",
        "methods": "",
    }


def _prefix_content(
    *,
    rel_path: str,
    kind: str,
    symbol: str = "",
    parent: str = "",
    imports: str = "",
    calls: str = "",
    attr_calls: str = "",
    methods: str = "",
    body: str,
) -> str:
    lines = [
        f"FILE: {rel_path}",
        f"KIND: {kind}",
    ]

    if symbol:
        lines.append(f"SYMBOL: {symbol}")
    if parent:
        lines.append(f"PARENT: {parent}")
    if imports:
        lines.append(f"IMPORTS: {imports}")
    if methods:
        lines.append(f"METHODS: {methods}")
    if calls:
        lines.append(f"CALLS: {calls}")
    if attr_calls:
        lines.append(f"ATTR_CALLS: {attr_calls}")

    return "\n".join(lines) + "\n\n" + body.strip()


def _iter_python_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"{module}: {names}" if module else names)

    out: list[str] = []
    seen: set[str] = set()

    for item in imports:
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)

    return out


def _top_level_nodes(tree: ast.AST) -> list[ast.AST]:
    out = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node)
    return out


def _extract_class_methods(node: ast.ClassDef) -> list[str]:
    methods: list[str] = []
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(child.name)
    return methods[:20]


def _module_header_text(text: str, top_nodes: list[ast.AST]) -> str:
    lines = text.splitlines()
    if not top_nodes:
        return text.strip()

    first_lineno = getattr(top_nodes[0], "lineno", 1)
    header = "\n".join(lines[: max(0, first_lineno - 1)]).strip()
    return header


def _attribute_chain(node: ast.AST) -> str | None:
    parts: list[str] = []
    cur = node

    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value

    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))

    return None


def _collect_call_hints(node: ast.AST) -> tuple[list[str], list[str]]:
    call_names: list[str] = []
    attr_calls: list[str] = []
    seen_names: set[str] = set()
    seen_attrs: set[str] = set()

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        func = child.func

        if isinstance(func, ast.Name):
            name = func.id.strip()
            if name and name not in seen_names:
                seen_names.add(name)
                call_names.append(name)

        elif isinstance(func, ast.Attribute):
            chain = _attribute_chain(func)
            if chain and chain not in seen_attrs:
                seen_attrs.add(chain)
                attr_calls.append(chain)

            attr_name = func.attr.strip()
            if attr_name and attr_name not in seen_names:
                seen_names.add(attr_name)
                call_names.append(attr_name)

    return call_names[:30], attr_calls[:30]


def _build_python_documents(path: Path, rel_path: str, text: str) -> list[Document]:
    docs: list[Document] = []

    try:
        tree = ast.parse(text)
    except Exception:
        return []

    ext = path.suffix.lower()
    imports = _iter_python_imports(tree)
    imports_s = " | ".join(imports[:20])
    top_nodes = _top_level_nodes(tree)

    header = _module_header_text(text, top_nodes)
    if header:
        module_calls, module_attr_calls = _collect_call_hints(tree)
        metadata = _base_metadata(rel_path, ext)
        metadata.update(
            {
                "kind": "module",
                "imports": imports_s,
                "calls": " | ".join(module_calls),
                "attr_calls": " | ".join(module_attr_calls),
            }
        )
        docs.append(
            Document(
                page_content=_prefix_content(
                    rel_path=rel_path,
                    kind="module",
                    imports=imports_s,
                    calls=" | ".join(module_calls),
                    attr_calls=" | ".join(module_attr_calls),
                    body=header,
                ),
                metadata=metadata,
            )
        )

    for node in top_nodes:
        segment = ast.get_source_segment(text, node)
        if not segment or not segment.strip():
            continue

        call_names, attr_calls = _collect_call_hints(node)
        calls_s = " | ".join(call_names)
        attr_calls_s = " | ".join(attr_calls)

        if isinstance(node, ast.ClassDef):
            kind = "class"
            symbol = node.name
            parent = ""
            methods = _extract_class_methods(node)
            methods_s = ", ".join(methods)
            body = segment
        else:
            kind = "function"
            symbol = node.name
            parent = ""
            methods_s = ""
            body = segment

        metadata = _base_metadata(rel_path, ext)
        metadata.update(
            {
                "kind": kind,
                "symbol": symbol,
                "parent": parent,
                "imports": imports_s,
                "calls": calls_s,
                "attr_calls": attr_calls_s,
                "methods": methods_s,
            }
        )

        docs.append(
            Document(
                page_content=_prefix_content(
                    rel_path=rel_path,
                    kind=kind,
                    symbol=symbol,
                    parent=parent,
                    imports=imports_s,
                    calls=calls_s,
                    attr_calls=attr_calls_s,
                    methods=methods_s,
                    body=body,
                ),
                metadata=metadata,
            )
        )

    if not docs:
        metadata = _base_metadata(rel_path, ext)
        docs.append(
            Document(
                page_content=_prefix_content(
                    rel_path=rel_path,
                    kind="file",
                    body=text,
                ),
                metadata=metadata,
            )
        )

    return docs


def _build_generic_documents(path: Path, rel_path: str, text: str) -> list[Document]:
    ext = path.suffix.lower()
    metadata = _base_metadata(rel_path, ext)

    raw_doc = Document(
        page_content=_prefix_content(
            rel_path=rel_path,
            kind="file",
            body=text,
        ),
        metadata=metadata,
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )

    return splitter.split_documents([raw_doc])


def _build_documents_for_file(path: Path, rel_path: str) -> list[Document]:
    text = _read_text(path)
    if not text:
        return []

    if path.suffix.lower() == ".py":
        py_docs = _build_python_documents(path, rel_path, text)
        if py_docs:
            return py_docs

    return _build_generic_documents(path, rel_path, text)


def _should_skip_rel_path(rel_path: str) -> bool:
    rel_posix = Path(rel_path).as_posix()

    if Path(rel_posix).name in SKIP_FILE_NAMES:
        return True

    parts = set(Path(rel_posix).parts)
    if parts & SKIP_PATH_PARTS:
        return True

    if any(rel_posix.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True

    if any(token in rel_posix for token in SKIP_SUBSTRINGS):
        return True

    return False


def _collect_documents() -> list[Document]:
    documents: list[Document] = []

    for root, dirs, files in os.walk(REPO_PATH):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            path = Path(root) / file
            ext = path.suffix.lower()
            if ext not in ALLOWED_EXT:
                continue

            rel_path = os.path.relpath(path, REPO_PATH)
            if _should_skip_rel_path(rel_path):
                continue

            documents.extend(_build_documents_for_file(path, rel_path))

    return documents


def _clear_db_dir() -> None:
    db_path = Path(DB_PATH)
    db_path.mkdir(parents=True, exist_ok=True)

    for child in db_path.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


documents = _collect_documents()

_clear_db_dir()

embedding = _quiet_embedding()

db = Chroma.from_documents(
    documents=documents,
    embedding=embedding,
    persist_directory=DB_PATH,
)

print(f"Repo indexed successfully. chunks={len(documents)}")
