"""Budget gate, log parsing, resume, and the tiny 16 GB recommendation."""

from __future__ import annotations

from pathlib import Path

import pytest

from plotweaver.errors import PlotweaverError
from plotweaver.fit16 import (
    BUDGET_BYTES,
    FIT_TARGET_MIB,
    families,
    merge_rows,
    parse_load_log,
    parse_perplexity,
    parse_tokens_per_second,
    probe_command,
    quality_loss,
    run_tiny,
    tiny_rows,
    within_budget,
)
from plotweaver.paths import repo_root


def test_families_cover_the_requested_quants() -> None:
    found = {family.id: family for family in families()}
    assert found["qwen3.6-27b-abliterated"].quants == ("IQ4_XS", "IQ3_M", "Q3_K_M")
    assert found["gemma-4-31b-abliterated"].quants == ("IQ4_XS", "IQ3_M", "Q3_K_M")
    assert found["mistral-small-3.2-24b-abliterated"].quants == ("Q4_K_M", "Q5_K_M")
    assert found["t-lite-it-2.1"].quants == ("Q5_K_M",)
    assert found["t-lite-it-2.1"].imatrix is False
    assert found["t-lite-it-2.1"].registry_quants == (("Q5_K_M", "t-lite-it-2.1-q5"),)
    pro = found["t-pro-it-2.1"]
    assert pro.quants == ("IQ4_XS", "IQ3_M")
    assert pro.imatrix is True
    assert pro.source_sha256.startswith("af2b3a76")
    assert pro.source_size == 34_816_397_344


def test_budget_is_thirteen_gib_and_a_spill_fails() -> None:
    assert FIT_TARGET_MIB == 13 * 1024
    assert within_budget(BUDGET_BYTES - 10, 9, False) is True
    assert within_budget(BUDGET_BYTES, 1, False) is False
    assert within_budget(1024, 1024, True) is False


def test_parse_vulkan_log_and_timings() -> None:
    log = "\n".join(
        [
            "llm_load_tensors: Vulkan0 model buffer size = 11000.00 MiB",
            "llama_kv_cache_unified: Vulkan0 KV buffer size = 700.50 MiB",
            "prompt eval time = 100.00 ms / 50 tokens (2.00 ms per token, 80.00 tokens per second)",
            "eval time = 200.00 ms / 16 runs (12.50 ms per token, 22.50 tokens per second)",
            "Final estimate: PPL = 7.25 +/- 0.10",
        ]
    )
    loaded = parse_load_log(log)
    assert within_budget(loaded.weight_bytes, loaded.kv_bytes, loaded.spilled) is True
    assert parse_tokens_per_second(log) == (80.0, 22.5)
    assert parse_perplexity(log) == 7.25
    spilled = "llm_load_tensors: CPU model buffer size = 500.00 MiB\n" + log
    assert parse_load_log(spilled).spilled is True


def test_probe_command_caps_the_24gb_card_at_the_16gb_budget() -> None:
    command = probe_command(
        Path("llama-cli"),
        Path("model.gguf"),
        context=16384,
        kv="q4_0",
        prompt="Напиши абзац.",
    )
    assert command[command.index("--fit-target") + 1] == "13312"
    assert command[command.index("-fa") + 1] == "on"
    assert command[command.index("-ctk") + 1] == "q4_0"
    assert command[command.index("-c") + 1] == "16384"


def test_quality_loss_rises_when_perplexity_or_the_synopsis_score_worsens() -> None:
    assert (
        quality_loss(
            perplexity=8.0,
            baseline_perplexity=8.0,
            synopsis_score=1.0,
            baseline_synopsis_score=1.0,
        )
        == 0.0
    )
    worse = quality_loss(
        perplexity=9.6,
        baseline_perplexity=8.0,
        synopsis_score=0.5,
        baseline_synopsis_score=1.0,
    )
    assert worse == pytest.approx(0.7)


def test_tiny_run_recommends_the_16k_row_and_resumes(tmp_path: Path) -> None:
    choice = run_tiny(tmp_path)
    assert choice is not None
    assert choice["model"] == "qwen3.6-27b-abliterated"
    assert choice["quant"] == "IQ3_M"
    assert choice["context"] == 16384
    assert choice["kv"] == "q4_0"
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Best 16 GB option" in text
    assert "FAIL" in text
    assert (tmp_path / "summary.csv").is_file()
    again = run_tiny(tmp_path)
    assert again == choice
    assert len(merge_rows(tiny_rows(), tiny_rows())) == len(tiny_rows())


def test_calibration_text_is_russian() -> None:
    text = (repo_root() / "bakeoff" / "calibration" / "ru-fiction.txt").read_text(encoding="utf-8")
    assert "Анна" in text
    assert len(text) > 1000


def test_missing_buffer_line_is_an_error() -> None:
    with pytest.raises(PlotweaverError, match="model buffer"):
        parse_load_log("no sizes here")
