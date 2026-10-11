"""Shared GGUF folder, registry licences, and the suite users file."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from plotweaver.domain import BookRequest, Language, ModelTier, request_from_dict, request_to_dict
from plotweaver.errors import PlotweaverError
from plotweaver.install import assign_book_models, ensure_default_install, ensure_uncensored_models
from plotweaver.llama_release import LLAMA_BUILD
from plotweaver.paths import (
    gguf_dir,
    llama_runtime_dir,
    models_dir,
    repo_root,
    shared_dir,
    shared_tools_dir,
)
from plotweaver.registry import (
    RegistryEntry,
    bakeoff_skip_reason,
    claim_user,
    detected_tier,
    download_model,
    import_forge_manifest,
    is_stock,
    load_registry,
    model_offered,
    resolve_tier,
    stock_for_tier,
    stored_filename,
    tier_capacity_gb,
    tier_headroom_gb,
    tier_option_enabled,
    uncensored_offer_allowed,
    usable_vram_gb,
    weight_path,
)
from plotweaver.settings import (
    model_tier_override,
    save_model_tier_override,
    save_uncensored_models,
    uncensored_models_preference,
)

_EXCLUDED = ("thedrummer", "heretic", "yandex")


def test_gguf_dir_is_the_shared_llm_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    monkeypatch.delenv("PLOTWEAVER_MODELS", raising=False)
    monkeypatch.delenv("VOXPRINT_MODELS_DIR", raising=False)
    monkeypatch.delenv("PLOTWEAVER_LLAMA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert shared_dir() == tmp_path / "shared"
    assert models_dir() == tmp_path / "models"
    assert gguf_dir() == tmp_path / "models" / "llm"
    assert llama_runtime_dir() == tmp_path / "shared" / "runtime" / f"llama.cpp-{LLAMA_BUILD}"
    assert shared_tools_dir() == tmp_path / "shared" / "tools"
    monkeypatch.setenv("PLOTWEAVER_MODELS", str(tmp_path / "override"))
    assert models_dir() == tmp_path / "override"
    assert gguf_dir() == tmp_path / "override" / "llm"


def test_registry_lists_confirmed_apache_models() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    assert [entry.id for entry in entries] == [
        "t-pro-it-2.1-q4",
        "gemma-4-12b-it-q4",
        "t-lite-it-2.1-q4",
        "t-lite-it-2.1-q5",
        "qwen3.6-27b-abliterated-iq4-xs",
        "qwen3.6-27b-abliterated-iq3-m",
        "qwen3.6-27b-abliterated-q3-k-m",
        "gemma-4-31b-abliterated-iq4-xs",
        "gemma-4-31b-abliterated-iq3-m",
        "gemma-4-31b-abliterated-q3-k-m",
        "gemma-4-31b-abliterated-iq3-xxs",
        "t-lite-it-2.1-abliterated-iq4-xs",
        "t-lite-it-2.1-abliterated-q5",
        "qwen3.6-27b-abliterated-q5",
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
    qwen_q3 = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q3-k-m")
    assert qwen_q3.role == "least-censored"
    assert qwen_q3.enabled is True
    assert qwen_q3.tier == "16gb"
    assert qwen_q3.repo == "Mitroshenkov87/voxprint-huihui-qwen36-27b"
    assert qwen_q3.revision == "cc596c1a74791b7fca57d037ef168dd57c76ed34"
    assert qwen_q3.filename == "Q3_K_M.gguf"
    assert qwen_q3.sha256 == "a52055204d9bd9208f4312951a2a68b32c4c68d54d6905c5386dbb552df58edf"
    assert qwen_q3.size == 13_500_736_128
    assert qwen_q3.min_vram_gb == 13
    assert qwen_q3.default is False
    qwen = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q5")
    assert qwen.role == "least-censored"
    assert qwen.enabled is True
    assert qwen.tier == "24gb"
    assert qwen.repo == qwen_q3.repo
    assert qwen.revision == qwen_q3.revision
    assert qwen.filename == "Huihui-Qwen3.6-27B-abliterated-ggml-model-Q5_K.gguf"
    assert qwen.sha256 == "a4fd0da6216fb8b9a74e25a688a118b001888b704e17f5c851c2bd80f4f5e284"
    assert qwen.size == 19_535_700_288
    assert qwen.min_vram_gb == 18.5
    gemma_31 = next(entry for entry in entries if entry.id == "gemma-4-31b-abliterated-q4")
    assert gemma_31.enabled is True
    assert gemma_31.tier == "24gb"
    assert gemma_31.repo == "Mitroshenkov87/voxprint-gemma4-31b"
    assert gemma_31.revision == "458a5cea1077218d72daf2e49334abe6eb1da930"
    assert gemma_31.sha256 == "380f2f50f441225e669ab1541220985387bf3933573cd2f4f7e667f3790e73a3"
    assert gemma_31.size == 18_687_057_536
    assert gemma_31.min_vram_gb == 18
    iq4 = next(entry for entry in entries if entry.id == "t-lite-it-2.1-abliterated-iq4-xs")
    q5_lite = next(entry for entry in entries if entry.id == "t-lite-it-2.1-abliterated-q5")
    assert iq4.enabled is True and q5_lite.enabled is True
    assert iq4.languages == ("ru",) and q5_lite.languages == ("ru",)
    assert iq4.tier == "16gb" and q5_lite.tier == "16gb"
    assert iq4.repo == "Mitroshenkov87/voxprint-t-lite-it-2.1"
    assert iq4.revision == "d06307f15311bc5d385c213ef82f52d6dc20ced3"
    assert q5_lite.revision == iq4.revision
    assert iq4.filename == "IQ4_XS.gguf"
    assert iq4.sha256 == "0f0d10020cd7186c5fa46eed0feb5007f5af7fdef01dcd90883e8fe5ee758df0"
    assert iq4.size == 4_561_837_632
    assert iq4.min_vram_gb == 5
    assert q5_lite.filename == "Q5_K_M.gguf"
    assert q5_lite.sha256 == "3a418e95f953f8d52c8f4047f8731bde37bc1874013bf22e2ea49216fa586b5d"
    assert q5_lite.size == 5_850_952_896
    assert q5_lite.min_vram_gb == 6.5
    waiting = next(entry for entry in entries if entry.id == "gemma-4-31b-abliterated-iq3-xxs")
    assert waiting.enabled is True
    assert waiting.revision == "26495e1a45d8bde085a0681c3c43044eff5c8ac5"
    assert waiting.sha256 == "c7bb8f9f4bdb396fb40a5beb617de27132cda6727b885e82f635340f353c5340"
    assert waiting.size == 12_077_502_368
    assert waiting.filename == "IQ3_XXS.gguf"
    assert waiting.min_vram_gb == 12
    fit = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-iq4-xs")
    assert fit.enabled is False
    assert fit.default is False
    assert fit.tier == "16gb"
    assert is_stock(lite)
    assert not is_stock(qwen)
    for entry in entries:
        if entry.enabled:
            assert entry.license == "apache-2.0"
            assert re.fullmatch(r"[0-9a-f]{64}", entry.sha256), entry.id
            assert re.fullmatch(r"[0-9a-f]{40}", entry.revision), entry.id
        assert entry.base_license == "apache-2.0"
        assert entry.base_repo
        assert entry.tier == entry.card
        assert entry.tier in {"16gb", "24gb"}
        blob = " ".join(
            [entry.id, entry.repo, entry.base_repo, entry.filename, entry.notes]
        ).lower()
        for banned in _EXCLUDED:
            assert banned not in blob
        assert "mistral" not in blob


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
    ]
    assert tier_headroom_gb(16) == 2
    assert tier_headroom_gb(24) == 3
    assert usable_vram_gb(16, 16) == 14
    assert detected_tier(16) == "16gb"
    assert detected_tier(23.4) == "16gb"
    assert detected_tier(23.99) == "24gb"
    assert detected_tier(24) == "24gb"
    assert tier_headroom_gb(23.99) == 3
    assert resolve_tier(16, "24gb") == "16gb"
    assert resolve_tier(23.4, "24gb") == "16gb"
    assert resolve_tier(23.99, "24gb") == "24gb"
    assert resolve_tier(24, "16gb") == "16gb"
    assert tier_option_enabled("24gb", total_gb=23.99, free_gb=2) is True
    assert tier_option_enabled("24gb", total_gb=16, free_gb=14) is False
    assert tier_option_enabled("24gb", total_gb=24, free_gb=20) is True
    assert uncensored_offer_allowed(16) is True
    assert uncensored_offer_allowed(20) is True
    assert uncensored_offer_allowed(24) is True
    assert uncensored_offer_allowed(8, 3) is True
    assert uncensored_offer_allowed(6, 1) is False
    t_pro_early = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    assert model_offered(t_pro_early, total_gb=23.99, free_gb=10) is True
    assert tier_capacity_gb(23.99) >= t_pro_early.min_vram_gb
    qwen = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q5")
    assert qwen.optional is True and qwen.uncensored is True
    assert qwen.tier == "24gb"
    assert model_offered(qwen, total_gb=16, free_gb=14) is False
    assert model_offered(qwen, total_gb=24, free_gb=22) is True
    assert bakeoff_skip_reason(qwen, free_gb=20) is None
    qwen_q3 = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q3-k-m")
    assert model_offered(qwen_q3, total_gb=16, free_gb=14) is True
    t_pro = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    assert is_stock(t_pro)
    assert t_pro.tier == "24gb"
    assert bakeoff_skip_reason(t_pro, free_gb=14)
    placeholder = next(entry for entry in entries if entry.id == "gemma-4-31b-abliterated-iq3-xxs")
    assert placeholder.enabled is True
    assert placeholder.tier == "16gb"


def test_dark_pass_uses_an_installed_forge_model_else_stock(tmp_path: Path) -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    qwen = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q5")
    qwen_q3 = next(entry for entry in entries if entry.id == "qwen3.6-27b-abliterated-q3-k-m")
    gemma_31 = next(entry for entry in entries if entry.id == "gemma-4-31b-abliterated-q4")
    gemma = next(entry for entry in entries if entry.filename == "gemma-4-12b-it-Q4_K_M.gguf")
    t_pro = next(entry for entry in entries if entry.id == "t-pro-it-2.1-q4")
    (tmp_path / gemma.filename).write_bytes(b"g")
    (tmp_path / t_pro.filename).write_bytes(b"p")
    request = BookRequest(title="T", language=Language.RU, synopsis="s", dark_themes=True)
    assign_book_models(request, free_gb=16, total_gb=16, store=tmp_path)
    assert request.main_model_id == "gemma-4-12b-it-q4"
    assert request.least_censored_model_id == "gemma-4-12b-it-q4"
    small = BookRequest(
        title="T",
        language=Language.RU,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(small, free_gb=16, total_gb=16, store=tmp_path)
    assert small.main_model_id == "gemma-4-12b-it-q4"
    (tmp_path / stored_filename(qwen_q3)).write_bytes(b"3")
    fitted = BookRequest(title="T", language=Language.EN, synopsis="s", dark_themes=True)
    assign_book_models(fitted, free_gb=14, total_gb=16, store=tmp_path)
    assert fitted.main_model_id == "gemma-4-12b-it-q4"
    assert fitted.least_censored_model_id == "qwen3.6-27b-abliterated-q3-k-m"
    (tmp_path / qwen.filename).write_bytes(b"q")
    (tmp_path / gemma_31.filename).write_bytes(b"G")
    request = BookRequest(title="T", language=Language.EN, synopsis="s", dark_themes=True)
    assign_book_models(request, free_gb=22, total_gb=24, store=tmp_path)
    assert request.main_model_id == "t-pro-it-2.1-q4"
    assert request.least_censored_model_id == "qwen3.6-27b-abliterated-q5"
    least = BookRequest(
        title="T",
        language=Language.EN,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(least, free_gb=22, total_gb=24, store=tmp_path)
    assert least.main_model_id == "qwen3.6-27b-abliterated-q5"
    assert least.least_censored_gguf == ""
    russian_small = BookRequest(
        title="T",
        language=Language.RU,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(russian_small, free_gb=16, total_gb=16, store=tmp_path)
    assert russian_small.main_model_id == "qwen3.6-27b-abliterated-q3-k-m"


def test_uncensored_count_does_not_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_download(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("download attempted")

    monkeypatch.setattr("plotweaver.registry.download_model", fail_download)
    assert ensure_default_install(free_gb=16, total_gb=16, store=tmp_path) == 0
    assert ensure_default_install(free_gb=22, total_gb=24, store=tmp_path) == 0
    with pytest.raises(PlotweaverError, match="least-censored"):
        ensure_uncensored_models(total_vram_gb=6, free_gb=1, store=tmp_path)
    assert ensure_uncensored_models(total_vram_gb=16, free_gb=14, store=tmp_path) == 0
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    for entry in entries:
        if entry.id in {
            "gemma-4-12b-it-q4",
            "t-lite-it-2.1-q4",
            "qwen3.6-27b-abliterated-q3-k-m",
            "gemma-4-31b-abliterated-iq3-xxs",
            "t-lite-it-2.1-abliterated-iq4-xs",
            "t-lite-it-2.1-abliterated-q5",
        }:
            (tmp_path / stored_filename(entry)).write_bytes(b"x")
    assert ensure_default_install(free_gb=16, total_gb=16, store=tmp_path) == 2
    assert ensure_uncensored_models(total_vram_gb=16, free_gb=14, store=tmp_path) == 4


def test_stock_for_tier_excludes_the_other_tier() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    assert [entry.id for entry in stock_for_tier(entries, total_gb=24)] == ["t-pro-it-2.1-q4"]
    assert [entry.id for entry in stock_for_tier(entries, total_gb=16)] == [
        "gemma-4-12b-it-q4",
        "t-lite-it-2.1-q4",
    ]


def test_fresh_24gb_install_does_not_download(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert ensure_default_install(free_gb=22, total_gb=24, store=fresh) == 0


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


def test_russian_book_prefers_the_forge_t_lite(tmp_path: Path) -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    for entry in entries:
        if entry.id in {
            "t-pro-it-2.1-q4",
            "gemma-4-31b-abliterated-q4",
            "qwen3.6-27b-abliterated-q5",
            "t-lite-it-2.1-abliterated-iq4-xs",
            "t-lite-it-2.1-abliterated-q5",
        }:
            (tmp_path / stored_filename(entry)).write_bytes(b"x")
    russian_book = BookRequest(
        title="T",
        language=Language.RU,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(russian_book, free_gb=22, total_gb=24, store=tmp_path)
    assert russian_book.main_model_id == "t-lite-it-2.1-abliterated-q5"
    english = BookRequest(
        title="T",
        language=Language.EN,
        synopsis="s",
        tier=ModelTier.LEAST_CENSORED,
    )
    assign_book_models(english, free_gb=22, total_gb=24, store=tmp_path)
    assert english.main_model_id == "qwen3.6-27b-abliterated-q5"


def test_import_forge_manifest_enables_one_placeholder(tmp_path: Path) -> None:
    registry = tmp_path / "models.toml"
    registry.write_text(
        (repo_root() / "bakeoff" / "models.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = tmp_path / "forge.json"
    digest = "ab" * 32
    manifest.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "qwen3.6-27b-abliterated-iq4-xs",
                        "revision": "ab" * 20,
                        "sha256": digest,
                        "size": 120,
                        "repo": "Mitroshenkov87/voxprint-model-forge",
                        "filename": "t-lite-forge.gguf",
                        "min_vram_gb": 6,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert import_forge_manifest(manifest, registry) == ["qwen3.6-27b-abliterated-iq4-xs"]
    filled = next(
        entry for entry in load_registry(registry) if entry.id == "qwen3.6-27b-abliterated-iq4-xs"
    )
    assert filled.enabled is True
    assert filled.revision == "ab" * 20
    assert filled.sha256 == digest
    assert filled.size == 120
    assert filled.repo == "Mitroshenkov87/voxprint-model-forge"
    assert filled.filename == "t-lite-forge.gguf"
    assert filled.min_vram_gb == 6
    assert filled.languages == ()
    with pytest.raises(PlotweaverError, match="stock"):
        import_forge_manifest(
            _manifest(tmp_path, "t-pro-it-2.1-q4"),
            registry,
        )
    with pytest.raises(PlotweaverError, match="not in the registry"):
        import_forge_manifest(_manifest(tmp_path, "missing-model"), registry)


def test_short_vram_names_the_holder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLOTWEAVER_FAKE_VRAM_HOLDERS", "4242,llama-server.exe,20000")
    request = BookRequest(title="T", language=Language.EN, synopsis="s")
    with pytest.raises(PlotweaverError, match=r"llama-server.exe \(pid 4242, 20000 MiB\)"):
        assign_book_models(request, free_gb=1, total_gb=4, store=tmp_path)


def test_generic_quant_moves_onto_the_model_id(tmp_path: Path) -> None:
    payload = b"weight"
    digest = hashlib.sha256(payload).hexdigest()
    entry = RegistryEntry(
        id="qwen3.6-27b-abliterated-q3-k-m",
        role="least-censored",
        repo="example/forge",
        filename="Q3_K_M.gguf",
        sha256=digest,
        size=len(payload),
        license="apache-2.0",
        min_vram_gb=13,
        context=8192,
        moe=False,
        notes="",
    )
    generic = tmp_path / "Q3_K_M.gguf"
    generic.write_bytes(payload)
    path = weight_path(tmp_path, entry)
    assert path.name == "qwen3.6-27b-abliterated-q3-k-m-Q3_K_M.gguf"
    assert path.read_bytes() == payload
    assert not generic.exists()
    stock = next(
        item
        for item in load_registry(repo_root() / "bakeoff" / "models.toml")
        if item.id == "gemma-4-12b-it-q4"
    )
    assert stored_filename(stock) == stock.filename
    bare = next(
        item
        for item in load_registry(repo_root() / "bakeoff" / "models.toml")
        if item.id == "t-lite-it-2.1-abliterated-q5"
    )
    assert stored_filename(bare) == "t-lite-it-2.1-abliterated-q5-Q5_K_M.gguf"


def test_import_forge_manifest_rejects_an_unpinned_revision(tmp_path: Path) -> None:
    registry = tmp_path / "models.toml"
    original = (repo_root() / "bakeoff" / "models.toml").read_bytes()
    registry.write_bytes(original)
    manifest = _manifest(tmp_path, "gemma-4-31b-abliterated-iq3-xxs")
    with pytest.raises(PlotweaverError, match="40-hex"):
        import_forge_manifest(manifest, registry, dry_run=True)
    assert registry.read_bytes() == original


def test_download_refuses_an_enabled_model_without_a_sha256(tmp_path: Path) -> None:
    payload = b"keep"
    entry = RegistryEntry(
        id="untagged",
        role="main",
        repo="example/model",
        filename="model.gguf",
        sha256="",
        size=len(payload),
        license="apache-2.0",
        min_vram_gb=1,
        context=8192,
        moe=False,
        notes="",
        revision="ab" * 20,
        base_repo="example/base",
        base_license="apache-2.0",
        tier="16gb",
        enabled=True,
    )
    target = tmp_path / entry.filename
    target.write_bytes(payload)
    with pytest.raises(PlotweaverError, match="no SHA-256"):
        download_model(entry, tmp_path)
    assert target.read_bytes() == payload
    assert not target.with_suffix(".gguf.partial").exists()


def _manifest(folder: Path, model_id: str) -> Path:
    path = folder / f"{model_id}.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": model_id,
                        "revision": "rev",
                        "sha256": "cd" * 32,
                        "size": 4,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path
