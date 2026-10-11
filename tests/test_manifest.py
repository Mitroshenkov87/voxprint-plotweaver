"""Shared manifest refcount, reuse of an existing GGUF, and repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from plotweaver.cli import main
from plotweaver.errors import PlotweaverError
from plotweaver.hardware import NVIDIA_DRIVER_PAGE, driver_status
from plotweaver.install import optional_notice
from plotweaver.manifest import (
    ManifestError,
    file_sha256,
    load_manifest,
    refuse_shared_delete,
    register_resource,
    unregister_app,
)
from plotweaver.paths import gguf_dir, legacy_models_dir, repo_root, shared_dir, voxprint_home
from plotweaver.registry import RegistryEntry, load_registry
from plotweaver.suite import _replace_tree, release_shared, repair_shared

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


def test_refcount_deletes_a_file_only_at_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    assert not marker.exists()
    assert marker.parent.is_dir()
    assert (shared / "runtime").is_dir()


def test_old_manifest_keeps_other_apps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    shared.mkdir(parents=True)
    target = shared / "models" / "llm" / "weights.gguf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abc")
    old = {
        "version": 1,
        "resources": {
            "example-model": {
                "kind": "model",
                "path": "models/llm",
                "bytes": 3,
                "files": {"weights.gguf": _DIGEST},
                "apps": ["audiobook-builder", "plotweaver"],
                "refcount": 2,
                "source": "example/gemma",
            }
        },
    }
    (shared / "manifest.json").write_text(json.dumps(old), encoding="utf-8")
    stored = load_manifest(shared)
    assert stored["example-model"].apps == ("audiobook-builder", "plotweaver")
    assert stored["example-model"].files["weights.gguf"] == _DIGEST
    rewritten = json.loads((shared / "manifest.json").read_text(encoding="utf-8"))
    assert rewritten["schema"] == 1
    refs = rewritten["components"]["example-model"]["refs"]
    assert refs == ["audiobook-builder", "plotweaver"]
    assert unregister_app(shared, "plotweaver") == []
    assert target.is_file()
    assert load_manifest(shared)["example-model"].apps == ("audiobook-builder",)


def test_mock_flag_names_the_dev_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import plotweaver.optional_mock as optional_mock

    monkeypatch.setattr(optional_mock, "_factory", None)
    with pytest.raises(PlotweaverError, match="dev extra"):
        optional_mock.mock_backend()


def test_uninstall_leaves_a_file_another_app_refs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    folder = shared / "models" / "llm"
    folder.mkdir(parents=True)
    shared_file = folder / "weights.gguf"
    own_file = folder / "only.gguf"
    shared_file.write_bytes(b"abc")
    own_file.write_bytes(b"abc")
    files = {"weights.gguf": _DIGEST}
    own = {"only.gguf": _DIGEST}
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
    register_resource(
        shared,
        "plotweaver-only",
        kind="model",
        path="models/llm",
        nbytes=3,
        files=own,
        app="plotweaver",
    )
    assert release_shared() == ["plotweaver-only"]
    assert shared_file.is_file()
    assert not own_file.exists()
    assert (shared / "models").is_dir()
    assert voxprint_home().is_dir()
    assert load_manifest(shared)["example-model"].apps == ("audiobook-builder",)


def test_shared_root_delete_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    home = voxprint_home()
    shared = shared_dir()
    roots = [
        home,
        shared,
        home / "models",
        home / "runtime",
        home / "voices",
        home / "cache",
        shared / "models",
        shared / "runtime",
        shared / "voices",
        shared / "cache",
    ]
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        marker = root / "keep.txt"
        marker.write_text("stay", encoding="utf-8")
        with pytest.raises(ManifestError, match="shared root"):
            refuse_shared_delete(root)
        assert marker.is_file()
    with pytest.raises(ManifestError, match="shared root"):
        refuse_shared_delete(home.parent)
    inside = shared / "models" / "llm" / "weights.gguf"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(b"abc")
    refuse_shared_delete(inside)


def test_shared_root_cannot_be_a_component(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    shared.mkdir(parents=True)
    blocked = [
        "models",
        "runtime",
        "voices",
        "cache",
        ".",
        "models/",
        "RUNTIME",
        "models/llm/..",
        str(voxprint_home()),
        str(shared),
        str(shared / "runtime"),
        str(shared / "models"),
    ]
    for path in blocked:
        with pytest.raises(ManifestError):
            register_resource(
                shared,
                "everything",
                kind="model",
                path=path,
                nbytes=0,
                files={},
                app="plotweaver",
            )
    assert not (shared / "manifest.json").is_file()


def test_uninstall_refuses_to_delete_a_shared_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    shared = shared_dir()
    models = shared / "models"
    keep = models / "llm" / "weights.gguf"
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b"abc")
    (shared / "runtime").mkdir()
    document = {
        "schema": 1,
        "components": {
            "everything": {
                "kind": "runtime",
                "version": "1",
                "path": "models",
                "sha256": _DIGEST,
                "installed_at": "2020-01-01T00:00:00",
                "refs": ["plotweaver"],
                "files": {"llm/weights.gguf": _DIGEST},
            }
        },
    }
    (shared / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match="shared root"):
        unregister_app(shared, "plotweaver")
    assert keep.is_file()
    assert models.is_dir()
    assert (shared / "runtime").is_dir()


def test_replace_tree_refuses_a_shared_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    root = shared_dir() / "runtime"
    root.mkdir(parents=True)
    marker = root / "keep.txt"
    marker.write_text("stay", encoding="utf-8")
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "file.txt").write_text("new", encoding="utf-8")
    with pytest.raises(ManifestError, match="shared root"):
        _replace_tree(source, root)
    assert marker.is_file()
    with pytest.raises(ManifestError, match="shared root"):
        _replace_tree(source, voxprint_home().parent)


def test_replace_tree_keeps_the_runtime_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    dest = shared_dir() / "runtime" / "python"
    dest.mkdir(parents=True)
    (dest / "old.txt").write_text("old", encoding="utf-8")
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "new.txt").write_text("new", encoding="utf-8")
    _replace_tree(source, dest)
    assert (dest / "new.txt").is_file()
    assert not (dest / "old.txt").exists()
    assert (shared_dir() / "runtime").is_dir()


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
    legacy = shared_dir() / "models" / "llm" / entry.filename
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"abc")
    users = legacy_models_dir() / ".users.json"
    users.parent.mkdir(parents=True)
    users.write_text('{"audiobook-builder": true}\n', encoding="utf-8")
    monkeypatch.setattr("plotweaver.suite.load_registry", lambda _path: [entry])

    notes: list[str] = []
    repaired = repair_shared(notes.append)
    dest = gguf_dir() / entry.filename
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


def test_repair_drops_a_corrupt_model_without_downloading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    entry = _entry()
    dest = gguf_dir() / entry.filename
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"zzz")
    monkeypatch.setattr("plotweaver.suite.load_registry", lambda _path: [entry])
    notes: list[str] = []
    assert repair_shared(notes.append) == []
    assert not dest.is_file()
    assert any("Repairing" in note for note in notes)
    assert any("not ready" in note.lower() for note in notes)


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
    assert "mdl-progress" in windows
    assert "--quiet" in windows
    assert "release-shared" in windows
    assert "mdl-progress --quiet --installer" in linux
    assert "plotweaver-mdl-install.log" in linux
    assert "voxprint/shared" in linux
    assert "mdl-progress --quiet --installer" in Path("packaging/assemble.py").read_text(
        encoding="utf-8"
    )
