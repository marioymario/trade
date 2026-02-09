#!/usr/bin/env bash
# ops/lockdown_8888_prepare.sh
# Makes docker-compose.yml bind port 8888 to localhost by default.
#
# Replaces common 8888 mappings with:
#   - "${JUPYTER_BIND_ADDR:-127.0.0.1}:8888:8888"
#
# Usage:
#   ./ops/lockdown_8888_prepare.sh
#   ./ops/lockdown_8888_prepare.sh path/to/compose.yml
#
# Then:
#   git diff

# set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="${1:-$REPO_ROOT/docker-compose.yml}"

if [[ ! -f "$FILE" ]]; then
  echo "ERROR: compose file not found: $FILE"
  exit 1
fi

ts="$(date +%F_%H%M%S)"
bak="${FILE}.bak.${ts}"
cp -a "$FILE" "$bak"
echo "Backup: $bak"

python3 - "$FILE" <<'PY'
import re
import sys

file_path = sys.argv[1]
with open(file_path, "r", encoding="utf-8") as f:
    s = f.read()

target_line = '- "${JUPYTER_BIND_ADDR:-127.0.0.1}:8888:8888"'

patterns = [
    r'^\s*-\s*"8888:8888"\s*$',
    r"^\s*-\s*'8888:8888'\s*$",
    r'^\s*-\s*8888:8888\s*$',

    r'^\s*-\s*"0\.0\.0\.0:8888:8888"\s*$',
    r"^\s*-\s*'0\.0\.0\.0:8888:8888'\s*$",
    r'^\s*-\s*0\.0\.0\.0:8888:8888\s*$',

    r'^\s*-\s*"127\.0\.0\.1:8888:8888"\s*$',
    r"^\s*-\s*'127\.0\.0\.1:8888:8888'\s*$",
    r'^\s*-\s*127\.0\.0\.1:8888:8888\s*$',
]

replaced = 0

lines = s.splitlines(True)  # keep line endings
out = []

for line in lines:
    new_line = line
    for p in patterns:
        if re.match(p, line):
            indent = re.match(r'^\s*', line).group(0)
            new_line = indent + target_line + ("\n" if line.endswith("\n") else "")
            replaced += 1
            break
    out.append(new_line)

new_s = "".join(out)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_s)

print(f"Replacements made: {replaced}")
if replaced == 0:
    print("NOTE: No matching 8888 port mapping lines found. Your compose may be structured differently.")
PY

echo
echo "=== After change: grep 8888 ==="
grep -nE '8888:8888|JUPYTER_BIND_ADDR' "$FILE" || true

echo
echo "Next:"
echo "  git diff"
echo "  git add docker-compose.yml && git commit -m \"Lock down 8888 to localhost\" && git push"
