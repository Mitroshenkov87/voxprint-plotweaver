"""Shared GGUF folder, registry licences, and the suite users file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.errors import PlotweaverError
from plotweaver.llama_release import LLAMA_BUILD
from plotweaver.paths import gguf_dir, llama_runtime_dir, models_dir, repo_root
from plotweaver.registry import claim_user, load_registry

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
        "qwen3.6-27b-abliterated-q4",
        "gemma-4-31b-abliterated-q4",
    ]
    shared = entries[1]
    assert shared.filename == "gemma-4-12b-it-Q4_K_M.gguf"
    assert shared.revision.startswith("fc034cff")
    assert shared.size == 7_121_861_440
    assert shared.card == "16gb"
    for entry in entries:
        assert entry.license == "apache-2.0"
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
role = "low-refusal"
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
