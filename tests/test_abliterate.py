"""Tiny ablation math, the produced registry row, and bake-off refusal rates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.abliterate import (
    PRODUCED_ID,
    difference_of_means,
    enable_produced_entry,
    orthogonalize,
    projection,
    refusal_rate,
    run_tiny,
    target_by_key,
)
from plotweaver.bakeoff import run_bakeoff
from plotweaver.errors import PlotweaverError
from plotweaver.paths import repo_root
from plotweaver.registry import load_registry


def test_direction_is_unit_and_orthogonalize_clears_it() -> None:
    direction = difference_of_means(
        [[1.0, 0.0], [0.8, 0.1]],
        [[0.0, 1.0], [0.1, 0.9]],
    )
    assert abs(sum(value * value for value in direction) - 1.0) < 1e-9
    matrix = [[1.0, 0.0], [0.0, 1.0]]
    # direction is 2-long; matrix out-dim must match. Rebuild a tall matrix.
    tall = [[1.0, 0.25], [0.0, 1.0]]
    if len(direction) != 2:
        raise AssertionError(direction)
    cleaned = orthogonalize(tall, direction)
    column = [row[0] for row in cleaned]
    assert projection(column, direction) < 1e-9
    assert matrix[0][0] == 1.0


def test_tiny_run_writes_a_card_and_drops_refusals(tmp_path: Path) -> None:
    report = run_tiny(tmp_path)
    assert report.kind == "tiny"
    assert report.refusal_after < report.refusal_before
    assert report.fits_16gb is True
    assert report.min_vram_gb == 15.0
    card = (tmp_path / f"{PRODUCED_ID}.MODEL_CARD.md").read_text(encoding="utf-8")
    assert "Apache-2.0" in card
    assert "Modification notice" in card
    assert report.base_revision in card
    assert report.sha256 in card
    assert "16 GB" in card
    lite = (tmp_path / "t-lite-it-2.1-plotweaver-abliterated-q4.MODEL_CARD.md").read_text(
        encoding="utf-8"
    )
    assert "T-Bank" in lite
    assert "Qwen" in lite
    assert "Modification notice" in lite
    pro = (tmp_path / "t-pro-it-2.1-plotweaver-abliterated-q4.MODEL_CARD.md").read_text(
        encoding="utf-8"
    )
    assert "does not fit a 16 GB card" in pro
    assert refusal_rate(["I cannot write this scene."]) == 1.0


def test_enable_produced_entry_records_the_hash(tmp_path: Path) -> None:
    source = repo_root() / "bakeoff" / "models.toml"
    path = tmp_path / "models.toml"
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    enable_produced_entry(path, model_id=PRODUCED_ID, sha256="ab" * 32, size=120, revision="rev-1")
    produced = next(entry for entry in load_registry(path) if entry.id == PRODUCED_ID)
    assert produced.enabled is True
    assert produced.sha256 == "ab" * 32
    assert produced.size == 120
    assert produced.revision == "rev-1"
    assert produced.optional is True
    assert produced.uncensored is True


def test_yandex_is_not_an_ablation_target() -> None:
    with pytest.raises(PlotweaverError, match="YandexGPT"):
        target_by_key("yandexgpt")
    assert target_by_key("t-lite").base_repo == "t-tech/T-lite-it-2.1"
    assert target_by_key("t-pro").credit.startswith("T-Bank")


def test_zero_direction_is_refused() -> None:
    with pytest.raises(PlotweaverError, match="zero length"):
        difference_of_means([[1.0, 1.0]], [[1.0, 1.0]])


def test_bakeoff_records_refusal_rates(tmp_path: Path) -> None:
    run_bakeoff(tmp_path, mock=True, limit=1)
    payload = json.loads((tmp_path / "refusal-rates.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in payload["models"]}
    assert by_id["mock-main"]["group"] == "stock"
    assert by_id["mock-low"]["group"] == "stock-least-censored"
    assert by_id["mock-low"]["refusal_rate"] < by_id["mock-main"]["refusal_rate"]
    assert payload["probe_count"] == 8
