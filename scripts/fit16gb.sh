#!/usr/bin/env bash
# Fit larger abliterated models into a 16 GB budget on the RTX 4090 VM.
# --tiny checks the table, the resume rule, and the recommendation. No weights.
# One command: bash scripts/fit16gb.sh
# A finished row in the results file is skipped, so the command can be repeated.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TINY=0
for arg in "$@"; do
  case "$arg" in
    --tiny) TINY=1 ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

pick_python() {
  if [[ -n "${PLOTWEAVER_PYTHON:-}" ]] && "$PLOTWEAVER_PYTHON" -c "import plotweaver" >/dev/null 2>&1; then
    echo "$PLOTWEAVER_PYTHON"
    return
  fi
  if [[ -x "$ROOT/.venv/bin/python" ]] && "$ROOT/.venv/bin/python" -c "import plotweaver" >/dev/null 2>&1; then
    echo "$ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -c "import plotweaver" >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  uv venv --python 3.14 "$ROOT/.venv"
  uv pip install --python "$ROOT/.venv/bin/python" -e "$ROOT"
  echo "$ROOT/.venv/bin/python"
}

PY="$(pick_python)"
OUT="${PLOTWEAVER_FIT_OUT:-$ROOT/out/fit16}"
if [[ "$TINY" == "1" ]]; then
  OUT="${PLOTWEAVER_FIT_OUT:-$ROOT/out/fit16-tiny}"
  exec "$PY" -m plotweaver.fit16 --tiny --out "$OUT"
fi
exec "$PY" -m plotweaver.fit16 --out "$OUT"
