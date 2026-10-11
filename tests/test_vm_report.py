"""VM test summary, the budget cap, and the sample brief."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from plotweaver.brief import parse_brief
from plotweaver.cli import main
from plotweaver.llama_server import append_completion_metric, apply_vram_budget_cap
from plotweaver.paths import repo_root
from plotweaver.vm_report import metric_totals, stage_wall_times, write_summary


def test_budget_cap_and_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PLOTWEAVER_VRAM_BUDGET_CAP_GB", raising=False)
    assert apply_vram_budget_cap(20) == 20
    monkeypatch.setenv("PLOTWEAVER_VRAM_BUDGET_CAP_GB", "nope")
    assert apply_vram_budget_cap(20) == 20
    monkeypatch.setenv("PLOTWEAVER_VRAM_BUDGET_CAP_GB", "14")
    assert apply_vram_budget_cap(20) == 14
    assert apply_vram_budget_cap(10) == 10
    path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("PLOTWEAVER_METRICS", str(path))
    append_completion_metric(
        model_id="m",
        prompt_tokens=3,
        completion_tokens=20,
        seconds=2,
    )
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["model"] == "m"
    assert row["tokens_per_second"] == 10
    totals = metric_totals(path)
    assert totals["completion_tokens"] == 20
    assert totals["tokens_per_second"] == 10
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4090,8.9,24576,20000")
    assert main(["doctor"]) == 0
    assert "capped at 14.0 GB" in capsys.readouterr().out


def test_stage_wall_times_sum_until_the_next_line() -> None:
    log = "\n".join(
        [
            "10.0\tstory bible",
            "12.5\toutline",
            "14.0\tbeats ch-01",
            "15.0\tdraft sc-01",
            "16.0\tload model",
            "19.0\tfill sc-01",
            "20.0\tEND",
        ]
    )
    times = stage_wall_times(log)
    assert times["story bible"] == 2.5
    assert times["outline"] == 1.5
    assert times["beats"] == 1.0
    assert times["draft"] == 1.0
    assert times["load"] == 3.0
    assert times["fill"] == 1.0
    assert "proofread" not in times


def test_summary_records_a_mock_pass(tmp_path: Path) -> None:
    (tmp_path / "mode.txt").write_text("1", encoding="utf-8")
    tier = tmp_path / "16gb"
    tier.mkdir()
    (tier / "run.json").write_text(
        json.dumps({"status": "completed", "refusals": 0}),
        encoding="utf-8",
    )
    (tier / "wall-seconds.txt").write_text("3.5", encoding="utf-8")
    (tier / "vram-peak-mib.txt").write_text("n/a", encoding="utf-8")
    (tier / "stderr.log").write_text("1.0\tstory bible\n2.0\tEND\n", encoding="utf-8")
    (tier / "vxbook-validate.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    summary = write_summary(tmp_path).read_text(encoding="utf-8")
    assert "Mode: mock." in summary
    assert "refusals: 0" in summary
    assert "story bible: 1.0 s" in summary
    assert "vxbook validate ok: True" in summary
    assert "bash scripts/vm_test.sh --mock" in summary


def test_vm_brief_is_short_and_dark() -> None:
    brief = parse_brief((repo_root() / "scripts" / "vm-brief.md").read_text(encoding="utf-8"))
    assert brief.language == "en"
    assert brief.dark_themes is True
    assert brief.chapter_count == 2
    assert brief.scenes_per_chapter == 1
    assert brief.target_words == 800


def test_summary_reads_powershell_encodings(tmp_path: Path) -> None:
    (tmp_path / "mode.txt").write_bytes("1".encode("utf-8-sig"))
    (tmp_path / "doctor.txt").write_bytes("NVIDIA\n".encode("utf-16"))
    summary = write_summary(tmp_path).read_text(encoding="utf-8")
    assert "Mode: mock." in summary
    assert "NVIDIA" in summary


def test_vm_test_ps1_writes_utf8_and_does_not_raise_none() -> None:
    text = (repo_root() / "scripts" / "vm_test.ps1").read_text(encoding="utf-8")
    assert "raise SystemExit(1) if info is None else print" not in text
    assert "print(detected_tier(info.total_gb)) if info else sys.exit(1)" in text
    assert "Out-File -Encoding utf8" in text
    assert "Invoke-Captured" in text
    assert "save_main_window" in text
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        assert " > " not in line
        assert ">(" not in line
        if "Invoke-Captured" in line:
            assert '""' not in line
    assert "out = ''" in text
    assert 'out = ""' not in text


def test_vm_test_script_parses() -> None:
    script = repo_root() / "scripts" / "vm_test.sh"
    powershell = repo_root() / "scripts" / "vm_test.ps1"
    text = script.read_text(encoding="utf-8")
    ps = powershell.read_text(encoding="utf-8")
    for flag in ("--smoke", "--json", "--mock"):
        assert flag in text
        assert flag in ps
    assert "-Smoke" in ps
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    subprocess.run([bash, "-n", str(script)], check=True)
