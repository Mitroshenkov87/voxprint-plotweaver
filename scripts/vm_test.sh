#!/usr/bin/env bash
# Lean RTX 4090 check: cheap tests, then one short dark-theme book per tier.
# Default output is ./out/vm-test. --mock skips the GPU and the model download.
# Settings are written under the output directory, not the machine's saved settings.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="./out/vm-test"
MOCK=0
SMOKE=0
JSON=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mock) MOCK=1; shift ;;
    --smoke) SMOKE=1; shift ;;
    --json) JSON=1; shift ;;
    --out)
      OUT="${2:-}"
      if [[ -z "$OUT" ]]; then
        echo "--out needs a directory" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done
if [[ "${PLOTWEAVER_MOCK:-}" == "1" ]]; then
  MOCK=1
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
  uv pip install --python "$ROOT/.venv/bin/python" --require-hashes --no-deps -r "$ROOT/packaging/requirements-common.txt"
  uv pip install --python "$ROOT/.venv/bin/python" --find-links "$ROOT/packaging/wheels" -e "$ROOT[dev]" -e "$ROOT/dev/plotweaver_dev"
  echo "$ROOT/.venv/bin/python"
}

if ! PY="$(pick_python)"; then
  echo "could not prepare Python" >&2
  exit 2
fi
if [[ "$MOCK" == "1" ]] && ! "$PY" -c "import plotweaver_dev" >/dev/null 2>&1; then
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  uv pip install --python "$PY" --find-links "$ROOT/packaging/wheels" -e "$ROOT[dev]" -e "$ROOT/dev/plotweaver_dev" || exit 2
fi
if ! "$PY" -m pytest --version >/dev/null 2>&1; then
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  uv pip install --python "$PY" --find-links "$ROOT/packaging/wheels" -e "$ROOT[dev]" -e "$ROOT/dev/plotweaver_dev"
fi

export PLOTWEAVER_NO_UPDATE_CHECK=1
export QT_QPA_PLATFORM=offscreen
export PLOTWEAVER_STATE="$OUT/state"
mkdir -p "$OUT/checks" "$OUT/screenshots" "$OUT/16gb" "$OUT/24gb" "$OUT/mars" "$OUT/state"
if [[ "$MOCK" == "1" ]]; then
  echo 1 > "$OUT/mode.txt"
else
  echo 0 > "$OUT/mode.txt"
fi

status=0

stop_plotweaver_llama() {
  local home="${HOME}/.local/share/voxprint"
  local install="/opt/voxprint-ai-suite/plotweaver"
  local pid cmd
  while read -r pid cmd; do
    case "$cmd" in
      "$home"*|"$install"*) kill "$pid" 2>/dev/null || true ;;
    esac
  done < <(ps -eo pid=,args= | awk '/llama-server/ && !/awk/')
}
trap stop_plotweaver_llama EXIT

mdl_ready() {
  if [[ "$MOCK" == "1" ]]; then
    echo skipped > "$OUT/checks/mdl-status.json"
    return 0
  fi
  if ! "$PY" -m voxprint_common.mdl status --app plotweaver --json >"$OUT/checks/mdl-status.json"; then
    return 1
  fi
  PLOTWEAVER_VM_MDL="$OUT/checks/mdl-status.json" "$PY" -c '
import json, os
from pathlib import Path
text = Path(os.environ["PLOTWEAVER_VM_MDL"]).read_text(encoding="utf-8").strip().splitlines()
payload = json.loads(text[-1]) if text else {}
raise SystemExit(0 if payload.get("ready") is True else 1)
'
}

stamp_copy() {
  local dest="$1"
  "$PY" -c '
import sys, time
dest = sys.argv[1]
with open(dest, "w", encoding="utf-8") as handle:
    for line in sys.stdin:
        handle.write(f"{time.time():.3f}\t{line}")
        handle.flush()
' "$dest"
}

start_vram_watch() {
  local dest="$1"
  echo 0 > "$dest"
  (
    peak=0
    while true; do
      used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d "[:space:]" || true)"
      if [[ "$used" =~ ^[0-9]+$ ]] && (( used > peak )); then
        peak=$used
        echo "$peak" > "$dest"
      fi
      sleep 2
    done
  ) &
  echo $!
}

save_shots() {
  local export_dir="${1:-}"
  PLOTWEAVER_VM_SHOTS="$OUT/screenshots" PLOTWEAVER_VM_EXPORT="$export_dir" "$PY" -c '
import os
from pathlib import Path
from plotweaver.ui.vm_shots import save_vm_shots
raw = os.environ.get("PLOTWEAVER_VM_EXPORT", "")
export = Path(raw) if raw else None
save_vm_shots(Path(os.environ["PLOTWEAVER_VM_SHOTS"]), export_dir=export)
'
}

save_main_window() {
  env -u QT_QPA_PLATFORM PLOTWEAVER_VM_OUT="$OUT" "$PY" -c '
from pathlib import Path
import os
from plotweaver.ui.vm_shots import save_main_window
save_main_window(Path(os.environ["PLOTWEAVER_VM_OUT"]) / "screenshots" / "main-window.png")
'
}

set_tier() {
  local tier="$1"
  PLOTWEAVER_VM_TIER="$tier" "$PY" -c '
import os
from plotweaver.settings import save_model_tier_override, save_uncensored_models
save_uncensored_models(True)
save_model_tier_override(os.environ["PLOTWEAVER_VM_TIER"])
'
}

json_line() {
  local code="$1"
  if [[ "$JSON" != "1" ]]; then
    return 0
  fi
  local ok="false"
  local mode="full"
  local mock="false"
  if [[ "$code" == "0" ]]; then
    ok="true"
  fi
  if [[ "$SMOKE" == "1" ]]; then
    mode="smoke"
  fi
  if [[ "$MOCK" == "1" ]]; then
    mock="true"
  fi
  printf '{"ok":%s,"exit":%s,"mode":"%s","mock":%s}\n' "$ok" "$code" "$mode" "$mock"
}

require_gpu() {
  if [[ "$MOCK" == "1" ]]; then
    return 0
  fi
  if "$PY" -c 'from plotweaver.hardware import is_supported, query_gpu
info = query_gpu()
raise SystemExit(0 if info is not None and is_supported(info) else 1)'; then
    return 0
  fi
  echo "no supported NVIDIA GPU" >&2
  json_line 3
  exit 3
}

detected_tier_name() {
  if [[ "$MOCK" == "1" ]]; then
    PLOTWEAVER_FAKE_GPU="NVIDIA GeForce RTX 4090,8.9,24564,20000" "$PY" -c '
from plotweaver.hardware import query_gpu
from plotweaver.registry import detected_tier
info = query_gpu()
if info is None:
    raise SystemExit(1)
print(detected_tier(info.total_gb))
'
  else
  "$PY" -c '
from plotweaver.hardware import query_gpu
from plotweaver.registry import detected_tier
info = query_gpu()
if info is None:
    raise SystemExit(1)
print(detected_tier(info.total_gb))
'
  fi
}

run_book() {
  local tier="$1"
  local chapters="${2:-2}"
  local scenes="${3:-1}"
  local dark="${4:-1}"
  local dir="$OUT/$tier"
  mkdir -p "$dir"
  local -a mock_args=()
  if [[ "$MOCK" == "1" ]]; then
    mock_args=(--mock)
    echo n/a > "$dir/vram-peak-mib.txt"
  else
    if [[ "$tier" == "16gb" ]]; then
      export PLOTWEAVER_VRAM_BUDGET_CAP_GB=14
      set_tier 16gb
    else
      unset PLOTWEAVER_VRAM_BUDGET_CAP_GB
      set_tier 24gb
    fi
    "$PY" -m plotweaver doctor > "$dir/doctor.txt"
  fi
  export PLOTWEAVER_METRICS="$dir/metrics.jsonl"
  : > "$dir/metrics.jsonl"
  local watch=""
  if [[ "$MOCK" != "1" ]]; then
    watch="$(start_vram_watch "$dir/vram-peak-mib.txt")"
  fi
  local start end code
  start="$(date +%s.%N)"
  set +e
  local -a dark_args=()
  if [[ "$dark" == "1" ]]; then
    dark_args=(--dark-themes)
  fi
  "$PY" -m plotweaver run \
    --project "$dir/project" \
    --brief "$ROOT/scripts/vm-brief.md" \
    --chapters "$chapters" \
    --scenes-per-chapter "$scenes" \
    --yes \
    --fb2 \
    --sound \
    --json \
    "${dark_args[@]+"${dark_args[@]}"}" \
    "${mock_args[@]+"${mock_args[@]}"}" \
    >"$dir/run.json" \
    2> >(stamp_copy "$dir/stderr.log")
  code=$?
  set -e
  end="$(date +%s.%N)"
  printf '%s\tEND\n' "$end" >> "$dir/stderr.log"
  VM_START="$start" VM_END="$end" "$PY" -c \
    'import os; print(float(os.environ["VM_END"]) - float(os.environ["VM_START"]))' \
    > "$dir/wall-seconds.txt"
  if [[ -n "$watch" ]]; then
    kill "$watch" 2>/dev/null || true
    wait "$watch" 2>/dev/null || true
  fi
  if [[ "$code" -ne 0 ]]; then
    return "$code"
  fi
  "$PY" -m plotweaver vxbook validate "$dir/project/export/book.vxbook" --json \
    > "$dir/vxbook-validate.json"
}

require_gpu

if [[ "$SMOKE" == "1" ]]; then
  echo "smoke install check"
  if ! "$PY" -c "import plotweaver"; then
    json_line 2
    exit 2
  fi
  echo "smoke doctor"
  if [[ "$MOCK" == "1" ]]; then
    "$PY" -m plotweaver doctor --mock >"$OUT/doctor.txt" || status=1
  else
    "$PY" -m plotweaver doctor >"$OUT/doctor.txt" || status=1
  fi
  echo "smoke models list"
  if ! "$PY" -m plotweaver models list --json >"$OUT/checks/models.json"; then
    status=1
  fi
  echo "smoke mdl status"
  if ! mdl_ready; then
    echo "models not ready" >&2
    status=1
  fi
  tier="$(detected_tier_name)" || status=1
  if [[ -n "${tier:-}" && "$status" -eq 0 ]]; then
    echo "smoke book $tier"
    run_book "$tier" 1 1 0 || status=1
    if [[ -f "$OUT/$tier/project/export/book.vxbook" ]]; then
      "$PY" -m plotweaver vxbook validate "$OUT/$tier/project/export/book.vxbook" --json \
        >"$OUT/$tier/vxbook-validate.json" || status=1
    else
      status=1
    fi
  fi
  echo "summary"
  PLOTWEAVER_VM_OUT="$OUT" "$PY" -c '
import os
from pathlib import Path
from plotweaver.vm_report import write_summary
write_summary(Path(os.environ["PLOTWEAVER_VM_OUT"]))
' || status=1
  json_line "$status"
  exit "$status"
fi

echo "pytest subset"
if ! "$PY" -m pytest \
  tests/test_models.py \
  tests/test_cli_machine.py \
  tests/test_vxbook.py \
  tests/test_ui.py::test_vm_shots \
  -q >"$OUT/checks/pytest.log" 2>&1; then
  status=1
fi

echo "CLI smoke"
if ! "$PY" -m plotweaver run \
  --project "$OUT/checks/dry-project" \
  --brief "$ROOT/scripts/vm-brief.md" \
  --chapters 2 \
  --scenes-per-chapter 1 \
  --dark-themes \
  --yes --fb2 --sound --json --dry-run --mock \
  >"$OUT/checks/run-dry.json"; then
  status=1
fi
if ! "$PY" -m plotweaver vxbook validate \
  "$ROOT/tests/fixtures/vxbook/manifest.json" \
  --dry-run --json >"$OUT/checks/vxbook-dry.json"; then
  status=1
fi
echo "screenshots"
if ! save_shots; then
  status=1
fi
echo "main window"
if ! save_main_window; then
  if [[ "$MOCK" == "1" ]]; then
    echo "main window skipped (no display)"
  else
    status=1
  fi
fi

if [[ "$MOCK" == "1" ]]; then
  mdl_ready || true
  echo "mock 16 GB pass"
  run_book 16gb || status=1
  echo "mock 24 GB pass"
  run_book 24gb || status=1
  echo "Mars hand-off"
  if ! PLOTWEAVER_MARS_OUT="$OUT/mars" bash "$ROOT/scripts/e2e_mars.sh" --mock; then
    status=1
  fi
else
  echo "GPU doctor"
  if ! "$PY" -m plotweaver doctor >"$OUT/doctor.txt"; then
    status=1
  fi
  if [[ "$status" -eq 0 ]]; then
    echo "mdl status"
    if ! mdl_ready; then
      echo "models not ready" >&2
      status=1
    fi
  fi
  if [[ "$status" -eq 0 ]]; then
    echo "16 GB pass"
    run_book 16gb || status=1
    detected="$(detected_tier_name)" || status=1
    if [[ "${detected:-}" == "24gb" ]]; then
      echo "24 GB pass"
      run_book 24gb || status=1
      export_dir="$OUT/24gb/project/export"
    else
      echo "24 GB pass skipped (card is ${detected:-unknown})"
      export_dir="$OUT/16gb/project/export"
    fi
    if [[ -f "$export_dir/book.vxbook" ]]; then
      save_shots "$export_dir" || status=1
    fi
    echo "Mars hand-off"
    if ! PLOTWEAVER_MARS_OUT="$OUT/mars" bash "$ROOT/scripts/e2e_mars.sh"; then
      status=1
    fi
  fi
fi

if [[ -f "$OUT/mars/book.vxbook" ]]; then
  "$PY" -m plotweaver vxbook validate "$OUT/mars/book.vxbook" --json \
    >"$OUT/mars/vxbook-validate.json" || status=1
fi
if [[ -f "$OUT/mars/book.sound.vxbook" ]]; then
  "$PY" -m plotweaver vxbook validate "$OUT/mars/book.sound.vxbook" --json \
    >"$OUT/mars/sound-validate.json" || status=1
fi

echo "summary"
PLOTWEAVER_VM_OUT="$OUT" "$PY" -c '
import os
from pathlib import Path
from plotweaver.vm_report import write_summary
write_summary(Path(os.environ["PLOTWEAVER_VM_OUT"]))
'
tar -C "$OUT" -czf "$OUT/vm-test-results.tar.gz" \
  summary.md screenshots doctor.txt 16gb 24gb mars checks state mode.txt 2>/dev/null \
  || tar -C "$OUT" -czf "$OUT/vm-test-results.tar.gz" \
    summary.md screenshots 16gb 24gb mars checks mode.txt

echo "wrote $OUT/summary.md and $OUT/vm-test-results.tar.gz"
json_line "$status"
exit "$status"
