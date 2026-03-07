#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE=(docker compose -f docker-compose.rag.yml)

ensure_rag_up() {
  "${COMPOSE[@]}" up -d rag >/dev/null 2>&1
}

run_quiet_exec() {
  local tmp
  tmp="$(mktemp)"
  if "${COMPOSE[@]}" exec -T rag "$@" 2> >(grep -vF "Warning: You are sending unauthenticated requests to the HF Hub." >"$tmp"); then
    cat "$tmp" >&2
    rm -f "$tmp"
    return 0
  else
    local rc=$?
    cat "$tmp" >&2
    rm -f "$tmp"
    return "$rc"
  fi
}

show_help() {
  cat <<'EOF'
Repo RAG Assistant

Usage:
  ./rag/rag.sh                 Start interactive prompt
  ./rag/rag.sh "question"      Ask one question
  ./rag/rag.sh index           Rebuild vector index
  ./rag/rag.sh eval            Run full eval suite
  ./rag/rag.sh eval --limit 5  Run partial eval suite
  ./rag/rag.sh status          Show container status
  ./rag/rag.sh help            Show this help

Notes:
  - Run from repo root or use this script directly.
  - Re-index after meaningful repo changes.
  - Interactive commands inside rag:
      :help    show prompt help
      :reload  reload vector DB
      :clear   clear screen
      :quit    exit
EOF
}

show_status() {
  ensure_rag_up
  "${COMPOSE[@]}" ps rag
}

run_eval() {
  python3 rag/eval_runner.py "$@"
}

if [ "$#" -eq 0 ]; then
  ensure_rag_up
  run_quiet_exec python query.py
  exit $?
fi

case "$1" in
index | reindex | --index)
  ensure_rag_up
  run_quiet_exec python ingest_repo.py
  ;;
eval)
  shift
  run_eval "$@"
  ;;
status)
  show_status
  ;;
help | --help | -h)
  show_help
  ;;
*)
  ensure_rag_up
  run_quiet_exec python query.py "$@"
  ;;
esac
