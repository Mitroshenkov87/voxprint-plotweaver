#!/usr/bin/env bash
# Write the short Russian Mars story, book.vxbook, and book.sound.vxbook.
# Default output is ./out/mars-e2e/. Override with PLOTWEAVER_MARS_OUT.
# PLOTWEAVER_MOCK=1 or --mock skips the GPU. A real run needs --main-gguf
# or PLOTWEAVER_MAIN_GGUF.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${PLOTWEAVER_MARS_OUT:-./out/mars-e2e}"
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
else
  has_gguf=0
  for arg in "${ARGS[@]+"${ARGS[@]}"}"; do
    if [[ "$arg" == "--main-gguf" ]]; then
      has_gguf=1
    fi
  done
  if [[ "$has_gguf" == "0" && -n "${PLOTWEAVER_MAIN_GGUF:-}" ]]; then
    ARGS+=("--main-gguf" "$PLOTWEAVER_MAIN_GGUF")
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
"$PY" -m plotweaver scenario-mars --yes --export-dir "$OUT" --project "$OUT/project" "${ARGS[@]+"${ARGS[@]}"}"
SOUND_ARGS=()
if [[ "$MOCK" == "1" ]]; then
  SOUND_ARGS+=(--mock)
fi
exec "$PY" -m plotweaver sound add "$OUT/book.vxbook" -o "$OUT/book.sound.vxbook" "${SOUND_ARGS[@]+"${SOUND_ARGS[@]}"}"
