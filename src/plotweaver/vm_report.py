"""Summary for one scripts/vm_test.sh run."""

from __future__ import annotations

import json
from pathlib import Path

from plotweaver.textio import read_text

_STAGES = (
    "story bible",
    "outline",
    "beats",
    "draft",
    "fill",
    "proofread",
    "load",
    "sound markup",
)


def stage_wall_times(log_text: str) -> dict[str, float]:
    """Sum seconds from each timestamped progress line until the next line."""
    events: list[tuple[float, str]] = []
    end: float | None = None
    for raw in log_text.splitlines():
        if "\t" not in raw:
            continue
        stamp, message = raw.split("\t", 1)
        try:
            when = float(stamp)
        except ValueError:
            continue
        text = message.strip()
        if text == "END":
            end = when
            continue
        name = _stage_name(text)
        if name is None:
            continue
        events.append((when, name))
    totals = {name: 0.0 for name in _STAGES}
    seen: set[str] = set()
    for index, (when, name) in enumerate(events):
        seen.add(name)
        if index + 1 < len(events):
            nxt = events[index + 1][0]
        elif end is not None:
            nxt = end
        else:
            nxt = when
        totals[name] += max(0.0, nxt - when)
    return {name: totals[name] for name in _STAGES if name in seen}


def metric_totals(path: Path) -> dict[str, float]:
    """Sum completion tokens and seconds, and the resulting tokens per second."""
    tokens = 0
    seconds = 0.0
    if path.is_file():
        for line in read_text(path).splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            tokens += int(row.get("completion_tokens") or 0)
            seconds += float(row.get("seconds") or 0)
    rate = (tokens / seconds) if seconds else 0.0
    return {
        "completion_tokens": float(tokens),
        "seconds": seconds,
        "tokens_per_second": rate,
    }


def write_summary(root: Path) -> Path:
    """Write summary.md for the directory scripts/vm_test.sh produced."""
    mode = "gpu"
    mode_path = root / "mode.txt"
    if mode_path.is_file() and read_text(mode_path).strip() == "1":
        mode = "mock"
    lines = [
        "# VM test",
        "",
        f"Mode: {mode}.",
        "",
        "Command: `bash scripts/vm_test.sh" + (" --mock" if mode == "mock" else "") + "`.",
        "",
        "Settings for this run live under `state/` in this folder. "
        "The machine's saved Plotweaver settings are not changed.",
        "",
        "## Checks",
        "",
        _check_line(root / "checks" / "pytest.log", "pytest"),
        _check_line(root / "checks" / "run-dry.json", "run --json --dry-run"),
        _check_line(root / "checks" / "vxbook-dry.json", "vxbook validate --json --dry-run"),
        _check_line(root / "checks" / "import-dry.json", "import-forge-manifest --json --dry-run"),
        "",
        "## GPU",
        "",
        _doctor_text(root / "doctor.txt"),
        "",
    ]
    if mode == "mock":
        lines.extend(
            [
                "The 16 GB and 24 GB folders below are mock passes. "
                "No GGUF was loaded and the 14 GB budget cap was not applied.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The 16 GB pass sets the tier override to 16 GB and "
                "`PLOTWEAVER_VRAM_BUDGET_CAP_GB=14` so the 24 GB card plans a 16 GB budget. "
                "The 24 GB pass clears that cap.",
                "",
            ]
        )
    lines.extend(_tier_section(root / "16gb", "16 GB"))
    lines.extend(_tier_section(root / "24gb", "24 GB"))
    lines.extend(_mars_section(root / "mars"))
    lines.extend(
        [
            "## Screenshots",
            "",
            "- `screenshots/brief-form.png`: new-book form after Help me write the brief.",
            "- `screenshots/progress.png`: progress screen mid-run.",
            "- `screenshots/result.png`: result screen with the export paths.",
            "- `screenshots/settings-tier.png`: Settings model tier panel.",
            "- `screenshots/main-window.png`: the real main window at 1920x1080.",
            "",
        ]
    )
    path = root / "summary.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _stage_name(message: str) -> str | None:
    for name in _STAGES:
        if message == name or message.startswith(name + " "):
            return name
    return None


def _check_line(path: Path, label: str) -> str:
    if path.is_file() and path.stat().st_size > 0:
        return f"- {label}: recorded in `{path.name}`."
    return f"- {label}: missing."


def _doctor_text(path: Path) -> str:
    if not path.is_file():
        return "Doctor output was not recorded."
    text = read_text(path).strip()
    if not text:
        return "Doctor output was empty."
    return text


def _tier_section(folder: Path, title: str) -> list[str]:
    lines = [f"## {title}", ""]
    if not folder.is_dir():
        lines.extend([f"{title} did not run.", ""])
        return lines
    report = _read_json(folder / "run.json")
    refusals = report.get("refusals", "n/a")
    status = report.get("status", "missing")
    wall = _read_text(folder / "wall-seconds.txt") or "n/a"
    peak = _peak_text(folder / "vram-peak-mib.txt")
    metrics = metric_totals(folder / "metrics.jsonl")
    if metrics["seconds"] <= 0:
        rate = "n/a (no llama-server metrics)"
    else:
        rate = (
            f"{metrics['tokens_per_second']:.2f} "
            f"({int(metrics['completion_tokens'])} completion tokens "
            f"in {metrics['seconds']:.1f} s)"
        )
    lines.extend(
        [
            f"- status: {status}",
            f"- refusals: {refusals}",
            f"- wall time: {wall} s",
            f"- peak VRAM: {peak}",
            f"- tokens/s: {rate}",
            "- stage wall time:",
        ]
    )
    stages = stage_wall_times(_read_text(folder / "stderr.log"))
    if not stages:
        lines.append("  - no progress lines")
    else:
        for name, seconds in stages.items():
            lines.append(f"  - {name}: {seconds:.1f} s")
    validate = _read_json(folder / "vxbook-validate.json")
    if validate:
        lines.append(f"- vxbook validate ok: {validate.get('ok')}")
    else:
        lines.append("- vxbook validate: missing")
    lines.append("")
    return lines


def _mars_section(folder: Path) -> list[str]:
    lines = ["## Mars hand-off", ""]
    book = folder / "book.vxbook"
    sound = folder / "book.sound.vxbook"
    lines.append(f"- book.vxbook: {'present' if book.is_file() else 'missing'}")
    lines.append(f"- book.sound.vxbook: {'present' if sound.is_file() else 'missing'}")
    validate = _read_json(folder / "vxbook-validate.json")
    if validate:
        lines.append(f"- vxbook validate ok: {validate.get('ok')}")
    lines.append("")
    return lines


def _peak_text(path: Path) -> str:
    text = _read_text(path)
    if not text or text == "n/a":
        return "n/a"
    if not text.isdigit():
        return text
    mib = int(text)
    return f"{mib} MiB ({mib / 1024:.2f} GB)"


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return read_text(path).strip()


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}
