"""Install, reuse, and repair the shared Voxprint files.

Shared files live under ``VOXPRINT_HOME/shared`` (or the platform default):
``runtime/``, ``models/``, and ``tools/``. A compatible file another Voxprint
app already installed is hard-linked after its size and SHA-256 match.
``manifest.json`` lists the apps that use each resource. Uninstall removes a
file only when Plotweaver was the last app.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from plotweaver.appinfo import version_label
from plotweaver.atomic import write_json
from plotweaver.errors import PlotweaverError
from plotweaver.fetch import format_size
from plotweaver.hardware import driver_status, is_supported, query_gpu
from plotweaver.llama_release import (
    CUDA_MARKER,
    LLAMA_BUILD,
    bundled_runtime_dir,
    ensure_pinned_runtime,
    pinned_asset,
    pinned_cuda_asset,
)
from plotweaver.manifest import (
    APP_ID,
    ManifestError,
    file_sha256,
    load_manifest,
    register_resource,
    unregister_app,
)
from plotweaver.paths import (
    gguf_dir,
    legacy_models_dir,
    llama_cuda_dir,
    llama_runtime_dir,
    repo_root,
    shared_dir,
    shared_runtime_dir,
    shared_tools_dir,
)
from plotweaver.registry import (
    RegistryEntry,
    claim_user,
    download_model,
    is_stock,
    load_registry,
    model_offered,
    registry_path,
    stored_filename,
    verify_file,
    weight_path,
)
from plotweaver.ui.i18n import tr

Progress = Callable[[str], None]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def repair_shared(progress: Progress | None = None) -> list[str]:
    """Check required shared files and replace missing or corrupt ones.

    Stock models download only when a supported GPU is present. Least-censored
    models are not part of this set.
    """
    say = progress or (lambda _message: None)
    say(tr("repair_checking"))
    for folder in (shared_runtime_dir(), gguf_dir(), shared_tools_dir()):
        folder.mkdir(parents=True, exist_ok=True)
    repaired: list[str] = []
    _record_python(say)
    _install_vulkan(say)
    status = driver_status()
    if not status.ok:
        say(status.message)
    else:
        say(status.message)
        _install_cuda(say)
    repaired.extend(_install_stock(say))
    claim_user(legacy_models_dir(), APP_ID)
    return repaired


def release_shared() -> list[str]:
    """Drop Plotweaver. Delete a shared file only when no app still uses it."""
    removed = unregister_app(shared_dir(), APP_ID)
    _drop_legacy_user(legacy_models_dir(), APP_ID)
    return removed


def selftest_report() -> dict[str, object]:
    """Repair shared files, then return one JSON-ready report. No traceback."""
    notes: list[str] = []
    error = ""
    repaired: list[str] = []
    try:
        repaired = repair_shared(notes.append)
    except PlotweaverError as exc:
        error = str(exc)
        notes.append(error)
    except OSError as exc:
        error = str(exc)
        notes.append(error)
    status = driver_status()
    resources = _resource_rows()
    if any(not bool(row["ok"]) for row in resources):
        error = error or "A shared file is missing or does not match its checksum."
    ok = error == "" and status.ok
    return {
        "ok": ok,
        "version": version_label(),
        "shared": str(shared_dir()),
        "driver": {
            "ok": status.ok,
            "version": status.version or "",
            "minimum": status.minimum,
            "message": status.message,
        },
        "repaired": repaired,
        "messages": notes,
        "resources": resources,
    }


def provision_main() -> int:
    """Installer entry. Progress goes to stderr. Failures stay one plain sentence."""
    try:
        repair_shared(lambda message: print(message, file=sys.stderr))
    except PlotweaverError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _resource_rows() -> list[dict[str, object]]:
    try:
        stored = load_manifest(shared_dir())
    except ManifestError as exc:
        return [{"id": "manifest", "ok": False, "detail": str(exc)}]
    rows: list[dict[str, object]] = []
    for key, resource in sorted(stored.items()):
        missing = [
            name for name in resource.files if not (shared_dir() / resource.path / name).is_file()
        ]
        rows.append({"id": key, "ok": not missing, "detail": ", ".join(missing)})
    return rows


def _install_stock(say: Progress) -> list[str]:
    if os.environ.get("PLOTWEAVER_SKIP_WEIGHTS"):
        return []
    gpu = query_gpu()
    if gpu is None or not is_supported(gpu):
        say(tr("models_skipped"))
        return []
    repaired: list[str] = []
    try:
        entries = load_registry(registry_path())
    except PlotweaverError as exc:
        raise PlotweaverError(str(exc)) from None
    for entry in entries:
        if not is_stock(entry):
            continue
        if not model_offered(entry, total_gb=gpu.total_gb, free_gb=gpu.free_gb):
            continue
        if _place_model(entry, say):
            repaired.append(entry.id)
    return repaired


def _place_model(entry: RegistryEntry, say: Progress) -> bool:
    """Return True when this call installed or repaired the file."""
    dest = weight_path(gguf_dir(), entry)
    local_name = stored_filename(entry)
    if dest.name != local_name:
        dest = gguf_dir() / local_name
    if _trusted(dest, size=entry.size, sha256=entry.sha256):
        _register_model(entry, _legacy_apps())
        return False
    if dest.is_file():
        say(tr("repair_broken").format(name=local_name))
        dest.unlink()
        _forget_stamp(dest)
    source = _matching_legacy(entry)
    if source is not None:
        say(tr("repair_reusing").format(name=local_name))
        _link_file(source, dest)
        verify_file(dest, size=entry.size, sha256=entry.sha256)
        _remember(dest, size=entry.size, sha256=entry.sha256)
        _register_model(entry, _legacy_apps())
        return True
    say(tr("repair_installing").format(name=local_name, size=format_size(entry.size)))
    download_model(entry, dest.parent, on_progress=say)
    _remember(dest, size=entry.size, sha256=entry.sha256)
    _register_model(entry, _legacy_apps())
    return True


def _matching_legacy(entry: RegistryEntry) -> Path | None:
    dest = gguf_dir() / stored_filename(entry)
    names = [stored_filename(entry)]
    if entry.filename not in names:
        names.append(entry.filename)
    for name in names:
        source = legacy_models_dir() / "llm" / name
        if not source.is_file():
            continue
        try:
            if source.resolve() == dest.resolve():
                continue
        except OSError:
            continue
        try:
            verify_file(source, size=entry.size, sha256=entry.sha256)
        except PlotweaverError, OSError:
            continue
        return source
    return None


def _register_model(entry: RegistryEntry, extra_apps: tuple[str, ...]) -> None:
    dest = gguf_dir() / stored_filename(entry)
    root = shared_dir().resolve()
    try:
        relative = dest.parent.resolve().relative_to(root).as_posix()
    except ValueError:
        return
    apps = tuple(dict.fromkeys((APP_ID, *extra_apps)))
    for app in apps:
        register_resource(
            shared_dir(),
            entry.id,
            kind="model",
            path=relative,
            nbytes=entry.size,
            files={stored_filename(entry): entry.sha256.lower()},
            app=app,
            source=entry.repo,
        )


def _legacy_apps() -> tuple[str, ...]:
    path = legacy_models_dir() / ".users.json"
    if not path.is_file():
        return ()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError, json.JSONDecodeError:
        return ()
    if not isinstance(loaded, dict):
        return ()
    return tuple(str(key) for key, value in loaded.items() if value)


def _drop_legacy_user(store: Path, user: str) -> None:
    path = store / ".users.json"
    if not path.is_file():
        return
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError, json.JSONDecodeError:
        return
    if not isinstance(loaded, dict) or user not in loaded:
        return
    data = {str(key): bool(value) for key, value in loaded.items() if str(key) != user}
    payload = json.dumps(data, indent=1, sort_keys=True)
    tmp = path.with_name(f".users.json.{os.urandom(4).hex()}.tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _install_vulkan(say: Progress) -> None:
    folder = llama_runtime_dir()
    if (folder / ".complete").is_file() and _marker_is(folder, LLAMA_BUILD):
        _register_runtime("llama-cpp-b11476-vulkan", folder, "vulkan")
        return
    bundled = _bundled_llama()
    if bundled is not None:
        say(tr("repair_reusing").format(name="llama.cpp b11476 Vulkan"))
        _replace_tree(bundled, folder)
        _register_runtime("llama-cpp-b11476-vulkan", folder, "vulkan")
        return
    asset = pinned_asset("windows" if sys.platform == "win32" else "linux")
    if asset is None:
        raise PlotweaverError("llama.cpp b11476 is published for Windows and Linux x64.")
    say(
        tr("repair_installing").format(
            name="llama.cpp b11476 Vulkan",
            size=format_size(asset.size),
        )
    )
    ensure_pinned_runtime(folder, asset, LLAMA_BUILD, on_progress=say)
    _register_runtime("llama-cpp-b11476-vulkan", folder, "vulkan")


def _install_cuda(say: Progress) -> None:
    folder = llama_cuda_dir()
    if (folder / ".complete").is_file() and _marker_is(folder, CUDA_MARKER):
        _register_runtime("llama-cpp-b11476-cuda", folder, "cuda")
        return
    asset = pinned_cuda_asset("windows" if sys.platform == "win32" else "linux")
    if asset is None:
        return
    say(tr("repair_installing").format(name="llama.cpp b11476 CUDA", size=format_size(asset.size)))
    ensure_pinned_runtime(folder, asset, CUDA_MARKER, on_progress=say)
    _register_runtime("llama-cpp-b11476-cuda", folder, "cuda")


def _bundled_llama() -> Path | None:
    try:
        folder = bundled_runtime_dir(repo_root())
    except FileNotFoundError:
        return None
    if _marker_is(folder, LLAMA_BUILD):
        return folder
    return None


def _marker_is(folder: Path, expected: str) -> bool:
    marker = folder / ".complete"
    if not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == expected
    except OSError:
        return False


def _register_runtime(resource_id: str, folder: Path, source: str) -> None:
    root = shared_dir().resolve()
    try:
        relative = folder.resolve().relative_to(root).as_posix()
    except ValueError:
        return
    marker = folder / ".complete"
    if not marker.is_file():
        return
    register_resource(
        shared_dir(),
        resource_id,
        kind="runtime",
        path=relative,
        nbytes=marker.stat().st_size,
        files={".complete": file_sha256(marker)},
        app=APP_ID,
        source=source,
    )


def _record_python(say: Progress) -> None:
    folder = shared_runtime_dir() / "python"
    if _python_ready(folder):
        _register_python(folder)
        return
    bundled = _bundled_python()
    if bundled is not None:
        say(tr("repair_reusing").format(name="Python"))
        _replace_tree(bundled, folder)
        _write_version_marker(folder)
        _register_python(folder)
        return
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": f"{sys.version_info[0]}.{sys.version_info[1]}",
        "executable": sys.executable,
    }
    write_json(folder / "interpreter.json", payload)
    _register_python(folder)


def _register_python(folder: Path) -> None:
    root = shared_dir().resolve()
    try:
        relative = folder.resolve().relative_to(root).as_posix()
    except ValueError:
        return
    tracked = _python_record(folder)
    if tracked is None:
        return
    register_resource(
        shared_dir(),
        "python-3.14",
        kind="runtime",
        path=relative,
        nbytes=tracked.stat().st_size,
        files={tracked.name: file_sha256(tracked)},
        app=APP_ID,
        source="python",
    )


def _python_record(folder: Path) -> Path | None:
    for name in ("VERSION", "interpreter.json"):
        path = folder / name
        if path.is_file():
            return path
    return None


def _python_ready(folder: Path) -> bool:
    binary = _find_python(folder)
    marker = folder / "VERSION"
    marker_text = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    if binary is not None and _marker_version(marker_text):
        return True
    pointer = folder / "interpreter.json"
    if pointer.is_file() and _pointer_ok(pointer):
        return True
    if binary is not None and _spawn_version_ok(binary):
        _write_version_marker(folder)
        return True
    return False


def _pointer_ok(pointer: Path) -> bool:
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    version = str(data.get("version") or "")
    executable = Path(str(data.get("executable") or ""))
    return _marker_version(version) and executable.is_file()


def _bundled_python() -> Path | None:
    try:
        folder = repo_root() / "python"
    except FileNotFoundError:
        return None
    binary = _find_python(folder)
    if binary is not None and _spawn_version_ok(binary):
        return folder
    return None


def _find_python(folder: Path) -> Path | None:
    for base in (folder, folder / "bin"):
        for name in ("python.exe", "python3", "python"):
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def _write_version_marker(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "VERSION").write_text("3.14\n", encoding="utf-8")


def _marker_version(text: str) -> bool:
    token = text.strip().split()[0] if text.strip() else ""
    parts = token.split(".")
    if len(parts) < 2:
        return False
    try:
        return (int(parts[0]), int(parts[1])) >= (3, 14)
    except ValueError:
        return False


def _spawn_version_ok(binary: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(binary), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError, subprocess.SubprocessError:
        return False
    return proc.returncode == 0 and _marker_version(proc.stdout.replace(" ", "."))


def _trusted(path: Path, *, size: int, sha256: str) -> bool:
    if not path.is_file():
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size != size:
        return False
    stamps = _load_stamps()
    row = stamps.get(path.name)
    if (
        isinstance(row, dict)
        and row.get("sha256") == sha256.lower()
        and int(row.get("size") or -1) == size
        and int(row.get("mtime_ns") or -1) == stat.st_mtime_ns
    ):
        return True
    try:
        verify_file(path, size=size, sha256=sha256)
    except PlotweaverError, OSError:
        return False
    _remember(path, size=size, sha256=sha256)
    return True


def _stamp_path() -> Path:
    return gguf_dir().parent / ".verify.json"


def _load_stamps() -> dict[str, object]:
    path = _stamp_path()
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    files = loaded.get("files") if isinstance(loaded, dict) else None
    if not isinstance(files, dict):
        return {}
    return {str(key): value for key, value in files.items()}


def _remember(path: Path, *, size: int, sha256: str) -> None:
    stamps = _load_stamps()
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return
    stamps[path.name] = {"size": size, "mtime_ns": mtime_ns, "sha256": sha256.lower()}
    write_json(_stamp_path(), {"files": stamps})


def _forget_stamp(path: Path) -> None:
    stamps = _load_stamps()
    if path.name not in stamps:
        return
    stamps.pop(path.name, None)
    write_json(_stamp_path(), {"files": stamps})


def _link_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def _replace_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, copy_function=_copy_link, symlinks=True)


def _copy_link(src: str, dest: str) -> None:
    source = Path(src)
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
