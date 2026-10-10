#!/usr/bin/env bash
# One-command Russian bake-off. On a GPU machine this downloads the registry
# GGUFs into <models>/llm and llama.cpp b11476 (Vulkan) beside them, then writes
# the books. PLOTWEAVER_MOCK=1 or --mock runs the deterministic path.
# Heretic is not downloaded or started. TheDrummer tunes are not in the registry.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MOCK=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --mock) MOCK=1 ;;
  esac
  ARGS+=("$arg")
done
if [[ "${PLOTWEAVER_MOCK:-}" == "1" ]]; then
  MOCK=1
fi
if [[ "$MOCK" == "1" ]]; then
  has_mock=0
  for arg in "${ARGS[@]+"${ARGS[@]}"}"; do
    if [[ "$arg" == "--mock" ]]; then
      has_mock=1
    fi
  done
  if [[ "$has_mock" == "0" ]]; then
    ARGS+=("--mock")
  fi
fi

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
exec "$PY" -m plotweaver bakeoff "${ARGS[@]+"${ARGS[@]}"}"
