"""Shared GGUF folder, registry licences, and the suite users file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.domain import BookRequest, Language, ModelTier, request_from_dict, request_to_dict
from plotweaver.errors import PlotweaverError
from plotweaver.install import assign_book_models, ensure_default_install, ensure_uncensored_models
from plotweaver.llama_release import LLAMA_BUILD
from plotweaver.paths import gguf_dir, llama_runtime_dir, models_dir, repo_root
from plotweaver.registry import (
    bakeoff_skip_reason,
    claim_user,
    detected_tier,
    is_stock,
    load_registry,
    model_offered,
    resolve_tier,
    tier_headroom_gb,
    tier_option_enabled,
    uncensored_offer_allowed,
    usable_vram_gb,
)
from plotweaver.settings import (
    model_tier_override,
    save_model_tier_override,
    save_uncensored_models,
    uncensored_models_preference,
)

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
        "t-lite-it-2.1-q5",
        "mistral-small-3.2-24b-q4",
        "mistral-small-3.2-24b-abliterated-q4",
        "mistral-small-3.2-24b-plotweaver-abliterated-q4",
        "t-lite-it-2.1-plotweaver-abliterated-q4",
        "t-pro-it-2.1-plotweaver-abliterated-q4",
        "qwen3.6-27b-abliterated-q4",
        "gemma-4-31b-abliterated-q4",
    ]
    shared = entries[1]
    assert shared.filename == "gemma-4-12b-it-Q4_K_M.gguf"
    assert shared.revision.startswith("fc034cff")
    assert shared.size == 7_121_861_440
    assert shared.card == "16gb"
    lite = next(entry for entry in entries if entry.id == "t-lite-it-2.1-q4")
    assert lite.role == "main"
    assert lite.card == "16gb"
    assert lite.tier == "16gb"
    assert lite.filename == "T-lite-it-2.1-Q4_K_M.gguf"
    assert lite.size == 5_027_750_240
    assert lite.sha256.startswith("68c75f59")
    lite_q5 = next(entry for entry in entries if entry.id == "t-lite-it-2.1-q5")
    assert lite_q5.role == "main"
    assert lite_q5.card == "16gb"
    assert lite_q5.filename == "T-lite-it-2.1-Q5_K_M.gguf"
    assert lite_q5.size == 5_850_952_544
    assert lite_q5.sha256.startswith("5ff7c6c3")
    assert lite_q5.revision == lite.revision
    mistral = next(entry for entry in entries if entry.id == "mistral-small-3.2-24b-q4")
    assert mistral.role == "least-censored"
    assert mistral.default is True
    assert mistral.card == "16gb"
    assert mistral.filename == "Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf"
    assert mistral.size == 14_333_922_848
    ablated = next(entry for entry in entries if entry.id == "mistral-small-3.2-24b-abliterated-q4")
    assert ablated.enabled is True
    assert ablated.optional is True
    assert ablated.uncensored is True
    assert ablated.size == 14_333_923_648
    assert not is_stock(ablated)
    assert is_stock(mistral)
    for entry in entries:
        if entry.enabled:
            assert entry.license == "apache-2.0"
            assert entry.revision
            assert entry.sha256
        assert entry.base_license == "apache-2.0"
        assert entry.base_repo
        assert entry.tier == entry.card
        assert entry.tier in {"16gb", "24gb"}
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
tier = "16gb"
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


def test_default_install_is_stock_and_bakeoff_keeps_abliterated_models() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    offered_16 = [
        entry.id
        for entry in entries
        if is_stock(entry) and model_offered(entry, total_gb=16, free_gb=16)
    ]
    assert offered_16 == [
        "gemma-4-12b-it-q4",
        "t-lite-it-2.1-q4",
        "t-lite-it-2.1-q5",
    ]
    offered_24 = [
        entry.id
        for entry in entries
        if is_stock(entry) and model_offered(entry, total_gb=24, free_gb=22)
    ]
    assert offered_24 == [
        "t-pro-it-2.1-q4",
        "gemma-4-12b-it-q4",
        "t-lite-it-2.1-q4",
        "t-lite-it-2.1-q5",
        "mistral-small-3.2-24b-q4",
    ]
    assert tier_headroom_gb(16) == 2
    assert tier_headroom_gb(24) == 3
    assert usable_vram_gb(16, 16) == 14
    assert detected_tier(16) == "16gb"
    assert detected_tier(24) == "24gb"
    assert resolve_tier(16, "24gb") == "16gb"
    assert resolve_tier(24, "16gb") == "16gb"
    assert tier_option_enabled("24gb", total_gb=16, free_gb=14) is False
    assert tier_option_enabled("24gb", total_gb=24, free_gb=20) is True
    assert uncensored_offer_allowed(16) is False
    assert uncensored_offer_allowed(20) is True
    qwen = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q4")
    assert qwen.optional is True and qwen.uncensored is True
    assert qwen.tier == "24gb"
    assert bakeoff_skip_reason(qwen, free_gb=20) is None
    t_pro = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    assert is_stock(t_pro)
    assert t_pro.tier == "24gb"
    assert bakeoff_skip_reason(t_pro, free_gb=14)
    placeholder = next(
        entry for entry in entries if entry.id == "t-lite-it-2.1-plotweaver-abliterated-q4"
    )
    assert placeholder.enabled is False
    assert placeholder.tier == "16gb"


def test_dark_pass_uses_an_installed_abliterated_model_else_stock(tmp_path: Path) -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    mistral = next(entry for entry in entries if entry.id == "mistral-small-3.2-24b-q4")
    qwen = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q4")
    gemma = next(entry for entry in entries if entry.filename == "gemma-4-12b-it-Q4_K_M.gguf")
    t_pro = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    (tmp_path / gemma.filename).write_bytes(b"g")
    (tmp_path / mistral.filename).write_bytes(b"m")
    (tmp_path / t_pro.filename).write_bytes(b"p")
    request = BookRequest(title="T", language=Language.RU, synopsis="s", dark_themes=True)
    assign_book_models(request, free_gb=16, total_gb=16, store=tmp_path)
    assert request.main_model_id == "gemma-4-12b-it-q4"
    assert request.least_censored_model_id == "gemma-4-12b-it-q4"
    (tmp_path / qwen.filename).write_bytes(b"q")
    request = BookRequest(title="T", language=Language.RU, synopsis="s", dark_themes=True)
    assign_book_models(request, free_gb=20, total_gb=24, store=tmp_path)
    assert request.main_model_id == "t-pro-it-2.1-q4"
    assert request.least_censored_model_id == "qwen3.6-27b-abliterated-q4"
    least = BookRequest(
        title="T",
        language=Language.RU,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
        dark_themes=True,
    )
    assign_book_models(least, free_gb=20, total_gb=24, store=tmp_path)
    assert least.main_model_id == "mistral-small-3.2-24b-q4"
    assert least.least_censored_gguf == ""
    small = BookRequest(
        title="T",
        language=Language.RU,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(small, free_gb=16, total_gb=16, store=tmp_path)
    assert small.main_model_id == "gemma-4-12b-it-q4"


def test_uncensored_download_is_separate_from_the_default_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    downloaded: list[str] = []

    def fake_download(entry, store, *, allow_other: bool = False):  # noqa: ANN001
        del allow_other
        downloaded.append(entry.id)
        target = store / entry.filename
        target.write_bytes(b"x")
        return target

    monkeypatch.setattr("plotweaver.install.download_model", fake_download)
    assert ensure_default_install(free_gb=16, total_gb=16, store=tmp_path) == 3
    assert "mistral-small-3.2-24b-q4" not in downloaded
    assert "t-pro-it-2.1-q4" not in downloaded
    assert ensure_default_install(free_gb=22, total_gb=24, store=tmp_path) == 2
    assert "qwen3.6-27b-abliterated-q4" not in downloaded
    assert "t-pro-it-2.1-q4" in downloaded
    assert "mistral-small-3.2-24b-q4" in downloaded
    with pytest.raises(PlotweaverError, match="20 GB"):
        ensure_uncensored_models(total_vram_gb=16, store=tmp_path)
    ensure_uncensored_models(total_vram_gb=24, store=tmp_path)
    assert "mistral-small-3.2-24b-abliterated-q4" in downloaded
    assert "gemma-4-31b-abliterated-q4" in downloaded


def test_uncensored_models_setting_defaults_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    assert uncensored_models_preference() is False
    save_uncensored_models(True)
    assert uncensored_models_preference() is True
    save_uncensored_models(False)
    assert uncensored_models_preference() is False
    assert model_tier_override() == "auto"
    save_model_tier_override("16gb")
    assert model_tier_override() == "16gb"
    t_pro = next(
        entry
        for entry in load_registry(repo_root() / "bakeoff" / "models.toml")
        if entry.id == "t-pro-it-2.1-q4"
    )
    assert model_offered(t_pro, total_gb=24, free_gb=22) is False
