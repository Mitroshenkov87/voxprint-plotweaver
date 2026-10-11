"""Shared manifest refcount, reuse of an existing GGUF, and repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from plotweaver.cli import main
from plotweaver.hardware import NVIDIA_DRIVER_PAGE, driver_status
from plotweaver.install import optional_notice
from plotweaver.manifest import (
    ManifestError,
    file_sha256,
    load_manifest,
    register_resource,
    unregister_app,
)
from plotweaver.paths import legacy_models_dir, repo_root, shared_dir
from plotweaver.registry import RegistryEntry, load_registry
from plotweaver.suite import release_shared, repair_shared

_DIGEST = hashlib.sha256(b"abc").hexdigest()


def _entry() -> RegistryEntry:
    return RegistryEntry(
        id="gemma-4-12b-it-q4",
        role="main",
        repo="example/gemma",
        filename="gemma.gguf",
        sha256=_DIGEST,
        size=3,
        license="apache-2.0",
        min_vram_gb=1,
        context=8192,
        moe=False,
        notes="",
        revision="abc",
        base_repo="example/base",
        base_license="apache-2.0",
        tier="16gb",
        enabled=True,
    )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("PLOTWEAVER_MODELS", raising=False)
    monkeypatch.delenv("PLOTWEAVER_LLAMA_DIR", raising=False)
    monkeypatch.setenv("PLOTWEAVER_FAKE_DRIVER", "570.120")
    monkeypatch.setenv(
        "PLOTWEAVER_FAKE_GPU",
        "NVIDIA GeForce RTX 4090,8.9,16384,14000",
    )
    monkeypatch.setattr("plotweaver.suite._install_vulkan", lambda _say: None)
    monkeypatch.setattr("plotweaver.suite._install_cuda", lambda _say: None)


def test_refcount_deletes_a_file_only_at_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    target = shared / "models" / "llm" / "weights.gguf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abc")
    files = {"weights.gguf": _DIGEST}
    register_resource(
        shared,
        "example-model",
        kind="model",
        path="models/llm",
        nbytes=3,
        files=files,
        app="plotweaver",
    )
    register_resource(
        shared,
        "example-model",
        kind="model",
        path="models/llm",
        nbytes=3,
        files=files,
        app="audiobook-builder",
    )
    stored = load_manifest(shared)["example-model"]
    assert stored.refcount == 2
    assert stored.apps == ("plotweaver", "audiobook-builder")
    assert unregister_app(shared, "plotweaver") == []
    assert target.is_file()
    assert load_manifest(shared)["example-model"].refcount == 1
    assert unregister_app(shared, "audiobook-builder") == ["example-model"]
    assert not target.exists()


def test_runtime_tree_is_removed_only_at_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    marker = shared / "runtime" / "python" / "VERSION"
    marker.parent.mkdir(parents=True)
    marker.write_text("3.14\n", encoding="utf-8")
    register_resource(
        shared,
        "python-3.14",
        kind="runtime",
        path="runtime/python",
        nbytes=marker.stat().st_size,
        files={"VERSION": file_sha256(marker)},
        app="plotweaver",
    )
    assert unregister_app(shared, "plotweaver") == ["python-3.14"]
    assert not marker.parent.exists()


def test_resource_path_cannot_escape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    with pytest.raises(ManifestError):
        register_resource(
            shared_dir(),
            "escape",
            kind="model",
            path="../outside",
            nbytes=0,
            files={},
            app="plotweaver",
        )


def test_reuse_links_a_verified_legacy_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    entry = _entry()
    legacy = legacy_models_dir() / "llm" / entry.filename
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"abc")
    users = legacy_models_dir() / ".users.json"
    users.write_text('{"audiobook-builder": true}\n', encoding="utf-8")
    monkeypatch.setattr("plotweaver.suite.load_registry", lambda _path: [entry])

    def fail_download(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("download attempted")

    monkeypatch.setattr("plotweaver.suite.download_model", fail_download)
    notes: list[str] = []
    repaired = repair_shared(notes.append)
    dest = shared_dir() / "models" / "llm" / entry.filename
    assert repaired == [entry.id]
    assert dest.is_file()
    assert dest.samefile(legacy)
    assert any("Reusing" in note for note in notes)
    stored = load_manifest(shared_dir())[entry.id]
    assert "plotweaver" in stored.apps
    assert "audiobook-builder" in stored.apps
    removed = release_shared()
    assert entry.id not in removed
    assert dest.is_file()
    assert load_manifest(shared_dir())[entry.id].apps == ("audiobook-builder",)
    assert legacy.is_file()
    text = json.loads((legacy_models_dir() / ".users.json").read_text(encoding="utf-8"))
    assert text["audiobook-builder"] is True
    assert "plotweaver" not in text


def test_repair_refetches_a_corrupt_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    entry = _entry()
    dest = shared_dir() / "models" / "llm" / entry.filename
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"zzz")
    monkeypatch.setattr("plotweaver.suite.load_registry", lambda _path: [entry])
    calls: list[str] = []

    def fake_download(item: RegistryEntry, store: Path, **_kwargs: object) -> Path:
        calls.append(item.id)
        target = store / item.filename
        target.write_bytes(b"abc")
        return target

    monkeypatch.setattr("plotweaver.suite.download_model", fake_download)
    notes: list[str] = []
    assert repair_shared(notes.append) == [entry.id]
    assert calls == [entry.id]
    assert dest.read_bytes() == b"abc"
    assert any("Repairing" in note for note in notes)


def test_old_driver_message_links_to_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_FAKE_DRIVER", "550.54.14")
    status = driver_status()
    assert status.ok is False
    assert "550.54.14" in status.message
    assert NVIDIA_DRIVER_PAGE in status.message


def test_optional_notice_includes_size_and_estimate() -> None:
    entries = load_registry(repo_root() / "bakeoff" / "models.toml")
    entry = next(item for item in entries if item.id == "qwen3.6-27b-abliterated-q3-k-m")
    text = optional_notice(entry)
    assert "Estimated time" in text
    assert "GB" in text


def test_selftest_json_reports_the_driver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "none")
    monkeypatch.setenv("PLOTWEAVER_SKIP_WEIGHTS", "1")
    assert main(["--selftest", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["driver"]["ok"] is True
    assert "570.120" in payload["driver"]["message"]
    monkeypatch.setenv("PLOTWEAVER_FAKE_DRIVER", "550.54.14")
    assert main(["--selftest", "--json"]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["ok"] is False
    assert NVIDIA_DRIVER_PAGE in failed["driver"]["message"]


def test_installers_provision_the_shared_folder() -> None:
    windows = Path("packaging/windows/plotweaver.iss").read_text(encoding="utf-8")
    linux = Path("packaging/linux/build-package.sh").read_text(encoding="utf-8")
    assert "plotweaver-provision.cmd" in windows
    assert "release-shared" in windows
    assert "plotweaver provision" in linux
    assert "voxprint/shared" in linux
    assert "plotweaver-provision.sh" in Path("packaging/assemble.py").read_text(encoding="utf-8")
