"""Version stamp and the bundled llama.cpp tree."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from plotweaver.appinfo import APP_VERSION, release_title, version_label
from plotweaver.llama_release import LLAMA_BUILD, bundled_runtime_dir, ensure_llama_server
from plotweaver.paths import _marked_root, repo_root


def test_version_is_shared() -> None:
    root = repo_root()
    payload = json.loads((root / "BUILD.json").read_text(encoding="utf-8"))
    assert payload["version"] == "0.2.0"
    assert payload["prerelease"] == "rc6"
    assert payload["codename"] == "Oreg"
    assert payload["build"] is None
    assert APP_VERSION == "0.2.0rc6"
    assert version_label() == '0.2.0 RC · build dev "Oreg"'
    assert release_title(52) == '0.2.0 RC · build 52 "Oreg"'
    assert list((root / "packaging" / "wheels").glob("voxprint_common-0.1.*.whl"))
    assert (root / "assets" / "splash.jpg").is_file()
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "voxprint-common==0.1.1" in project
    wheels = root / "packaging" / "wheels"
    assert (wheels / "voxprint_common-0.1.1-py3-none-any.whl").is_file()
    assert (wheels / "voxprint_common-0.1.1-py3-none-any.whl.sha256").is_file()
    assert (wheels / "voxprint_common-0.1.1.tar.gz").is_file()
    assert (wheels / "voxprint_common-0.1.1.tar.gz.sha256").is_file()
    assert "file:packaging/wheels" not in project
    installer = (root / "packaging" / "windows" / "plotweaver.iss").read_text(encoding="utf-8")
    windows = (root / "packaging" / "windows" / "build-installer.ps1").read_text(encoding="utf-8")
    linux = (root / "packaging" / "linux" / "build-package.sh").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--find-links" in workflow
    assert 'version = {attr = "plotweaver.appinfo.APP_VERSION"}' in project
    assert 'MyAppVersion "0.2.0rc1"' not in installer
    assert 'MyAppVersion "0.2.0rc2"' not in installer
    assert 'MyAppVersion "0.2.0rc3"' not in installer
    assert 'MyAppVersion "0.2.0rc4"' not in installer
    assert 'MyAppVersion "0.2.0rc5"' not in installer
    assert "BUILD.json supplies MyAppVersion" in installer
    assert "APP_VERSION" in windows
    assert "APP_VERSION" in linux
    assert "release_title" in workflow


def test_ci_verifies_tool_archives_and_drops_checkout_credentials() -> None:
    root = repo_root()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docs = (root / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    epub = "33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c  epubcheck.zip"
    leaks = "a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb  gitleaks.tar.gz"
    assert epub in ci
    assert leaks in ci
    assert ci.index(epub) < ci.index("unzip -q epubcheck.zip")
    assert ci.index(leaks) < ci.index("tar -xzf gitleaks.tar.gz")
    assert ci.count("persist-credentials: false") == 5
    assert docs.count("persist-credentials: false") == 1
    assert "contents: read" in ci.split("jobs:", 1)[0]
    assert "contents: write" in ci.split("release:", 1)[1].split("steps:", 1)[0]


def test_appinfo_does_not_import_the_package() -> None:
    tree = ast.parse(
        (repo_root() / "src" / "plotweaver" / "appinfo.py").read_text(encoding="utf-8")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("plotweaver") for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("plotweaver")


def test_choose_cpython_prefers_the_patch_install(tmp_path: Path) -> None:
    alias = tmp_path / "cpython-3.14-windows-x86_64-none"
    concrete = tmp_path / "cpython-3.14.8-windows-x86_64-none"
    alias.mkdir()
    concrete.mkdir()
    spec = importlib.util.spec_from_file_location(
        "assemble", repo_root() / "packaging" / "assemble.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.choose_cpython([alias, concrete]) == concrete


def test_marked_root_needs_both_markers(tmp_path: Path) -> None:
    assert _marked_root(tmp_path) is None
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert _marked_root(tmp_path) is None
    (tmp_path / "bakeoff").mkdir()
    assert _marked_root(tmp_path) == tmp_path


def test_bundled_runtime_is_used_before_a_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "app"
    binary = bundled_runtime_dir(root) / "llama-server"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"")
    (binary.parent / ".complete").write_text(LLAMA_BUILD, encoding="utf-8")
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_DRIVER", "none")
    monkeypatch.delenv("PLOTWEAVER_LLAMA_SERVER", raising=False)
    monkeypatch.setattr("plotweaver.llama_release.repo_root", lambda: root)
    monkeypatch.setattr(
        "plotweaver.llama_release.llama_runtime_dir", lambda: tmp_path / "shared-missing"
    )

    def fail_download(folder: Path) -> Path:
        raise AssertionError(f"download attempted: {folder}")

    monkeypatch.setattr("plotweaver.llama_release._ensure_in", fail_download)
    assert ensure_llama_server() == binary
