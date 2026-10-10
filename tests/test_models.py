"""Shared GGUF folder, registry licences, and the suite users file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.domain import ModelTier, request_from_dict, request_to_dict
from plotweaver.errors import PlotweaverError
from plotweaver.llama_release import LLAMA_BUILD
from plotweaver.paths import gguf_dir, llama_runtime_dir, models_dir, repo_root
from plotweaver.registry import (
    claim_user,
    download_decision,
    download_model,
    load_registry,
)
from plotweaver.settings import optional_models_preference, save_optional_models

_EXCLUDED = ("thedrummer", "heretic", "yandex")


def test_gguf_dir_is_the_shared_llm_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLOTWEAVER_MODELS", str(tmp_path))
    monkeypatch.delenv("PLOTWEAVER_LLAMA_DIR", raising=False)
    assert models_dir() == tmp_path
    assert gguf_dir() == tmp_path / "llm"
    assert llama_runtime_dir() == tmp_path / "llm" / f"llama.cpp-{LLAMA_BUILD}"


def test_registry_lists_confirmed_apache_models() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    assert [entry.id for entry in entries] == [
        "t-pro-it-2.1-q4",
        "gemma-4-12b-it-q4",
        "t-lite-it-2.1-q4",
        "mistral-small-3.2-24b-q4",
        "mistral-small-3.2-24b-abliterated-q4",
        "qwen3.6-27b-abliterated-q4",
        "gemma-4-31b-abliterated-q4",
    ]
    shared = entries[1]
    assert shared.filename == "gemma-4-12b-it-Q4_K_M.gguf"
    assert shared.revision.startswith("fc034cff")
    assert shared.size == 7_121_861_440
    assert shared.card == "16gb"
    lite = entries[2]
    assert lite.role == "main"
    assert lite.card == "16gb"
    assert lite.filename == "T-lite-it-2.1-Q4_K_M.gguf"
    assert lite.size == 5_027_750_240
    assert lite.sha256.startswith("68c75f59")
    mistral = entries[3]
    assert mistral.role == "least-censored"
    assert mistral.default is True
    assert mistral.card == "16gb"
    assert mistral.filename == "Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf"
    assert mistral.size == 14_333_922_848
    placeholder = entries[4]
    assert placeholder.enabled is False
    assert placeholder.sha256 == ""
    for entry in entries:
        if entry.enabled:
            assert entry.license == "apache-2.0"
            assert entry.revision
            assert entry.sha256
        assert entry.base_license == "apache-2.0"
        assert entry.base_repo
        blob = " ".join(
            [entry.id, entry.repo, entry.base_repo, entry.filename, entry.notes]
        ).lower()
        for banned in _EXCLUDED:
            assert banned not in blob


def test_registry_rejects_a_row_without_a_base_licence(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        """
[[model]]
id = "untagged"
role = "least-censored"
repo = "someone/tune"
revision = "abc"
filename = "tune.gguf"
sha256 = "aa"
size = 1
license = "apache-2.0"
base_repo = "someone/base"
""",
        encoding="utf-8",
    )
    with pytest.raises(PlotweaverError, match="base_license"):
        load_registry(path)


def test_old_low_refusal_project_reads_as_least_censored() -> None:
    loaded = request_from_dict(
        {
            "title": "T",
            "language": "ru",
            "synopsis": "s",
            "tier": "low-refusal",
            "low_refusal_gguf": "old.gguf",
            "low_refusal_model_id": "old",
        }
    )
    assert loaded.tier is ModelTier.LEAST_CENSORED
    assert loaded.least_censored_gguf == "old.gguf"
    assert loaded.least_censored_model_id == "old"
    stored = request_to_dict(loaded)
    assert stored["tier"] == "least-censored"
    assert stored["least_censored_gguf"] == "old.gguf"
    assert "low_refusal_gguf" not in stored


def test_users_file_keeps_other_suite_apps(tmp_path: Path) -> None:
    original = '{\n "audiobook-builder": true,\n "movie-dubber": true\n}'
    (tmp_path / ".users.json").write_text(original, encoding="utf-8")
    claim_user(tmp_path)
    text = (tmp_path / ".users.json").read_text(encoding="utf-8")
    users = json.loads(text)
    assert users["audiobook-builder"] is True
    assert users["movie-dubber"] is True
    assert users["plotweaver"] is True
    again = text
    claim_user(tmp_path)
    assert (tmp_path / ".users.json").read_text(encoding="utf-8") == again


def test_optional_download_follows_vram_unless_settings_say_otherwise() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    large = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    small = next(entry for entry in entries if entry.id == "t-lite-it-2.1-q4")
    held = next(entry for entry in entries if entry.id == "mistral-small-3.2-24b-abliterated-q4")
    assert download_decision(large, free_gb=22, total_vram_gb=16, optional_preference=None)
    assert download_decision(large, free_gb=22, total_vram_gb=24, optional_preference=None) is None
    assert download_decision(large, free_gb=22, total_vram_gb=24, optional_preference=False)
    assert download_decision(large, free_gb=22, total_vram_gb=16, optional_preference=True) is None
    assert download_decision(small, free_gb=14, total_vram_gb=16, optional_preference=None) is None
    assert download_decision(held, free_gb=24, total_vram_gb=24, optional_preference=True)


def test_disabled_placeholder_is_not_downloaded(tmp_path: Path) -> None:
    held = next(
        entry
        for entry in load_registry(repo_root() / "bakeoff" / "models.toml")
        if entry.id == "mistral-small-3.2-24b-abliterated-q4"
    )
    with pytest.raises(PlotweaverError, match="disabled"):
        download_model(held, tmp_path)


def test_optional_models_setting_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    assert optional_models_preference() is None
    save_optional_models(True)
    assert optional_models_preference() is True
    save_optional_models(False)
    assert optional_models_preference() is False
