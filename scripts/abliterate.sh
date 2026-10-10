#!/usr/bin/env bash
# Ablate one official Apache-2.0 model, then optionally the bake-off.
# Usage: bash scripts/abliterate.sh mistral|t-lite|t-pro [--bakeoff]
#        bash scripts/abliterate.sh --tiny
# --tiny runs the in-memory check used by CI. Heretic is not downloaded or started.
# YandexGPT is refused: its licence forbids modification and redistribution.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TINY=0
BAKE=0
MODEL=""
for arg in "$@"; do
  case "$arg" in
    --tiny) TINY=1 ;;
    --bakeoff) BAKE=1 ;;
    mistral|t-lite|t-pro) MODEL="$arg" ;;
    *)
      echo "unknown argument: $arg" >&2
      echo "usage: bash scripts/abliterate.sh mistral|t-lite|t-pro [--bakeoff]" >&2
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
if [[ "$TINY" == "1" ]]; then
  "$PY" -m plotweaver.abliterate --tiny --out "${PLOTWEAVER_ABLATE_OUT:-$ROOT/out/abliterate-tiny}"
else
  if [[ -z "$MODEL" ]]; then
    echo "name a model: mistral, t-lite, or t-pro" >&2
    exit 1
  fi
  "$PY" -m plotweaver.abliterate "$MODEL"
fi
if [[ "$BAKE" == "1" ]]; then
  bash "$ROOT/scripts/bakeoff.sh"
fi
