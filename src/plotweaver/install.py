"""Default stock downloads, and the separate abliterated download from Settings.

The first real run fetches stock models that fit the free VRAM. Abliterated
models stay out of that set. Settings can download them when the GPU has at
least 20 GB. A dark-theme book uses an installed abliterated file when one is
present, and otherwise the stock least-censored model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import assert_never

from plotweaver.domain import BookRequest, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.hardware import require_supported_gpu
from plotweaver.paths import gguf_dir
from plotweaver.registry import (
    RegistryEntry,
    download_model,
    fits_vram,
    is_stock,
    load_registry,
    registry_path,
    uncensored_offer_allowed,
)


def ensure_default_install(*, free_gb: float, store: Path | None = None) -> int:
    """Download stock models that fit. Skip files already in the shared folder."""
    folder = store or gguf_dir()
    count = 0
    for entry in load_registry(registry_path()):
        if not is_stock(entry) or not fits_vram(entry, free_gb):
            continue
        if (folder / entry.filename).is_file():
            continue
        download_model(entry, folder)
        count += 1
    return count


def ensure_uncensored_models(*, total_vram_gb: float, store: Path | None = None) -> int:
    """Download abliterated models. Refused below 20 GB of VRAM."""
    if not uncensored_offer_allowed(total_vram_gb):
        raise PlotweaverError("Abliterated models need a GPU with at least 20 GB of VRAM.")
    folder = store or gguf_dir()
    count = 0
    for entry in load_registry(registry_path()):
        if not entry.enabled or not entry.uncensored:
            continue
        if entry.min_vram_gb > total_vram_gb + 0.5:
            continue
        if (folder / entry.filename).is_file():
            continue
        download_model(entry, folder)
        count += 1
    return count


def assign_book_models(request: BookRequest, *, free_gb: float, store: Path) -> None:
    """Fill empty model paths. Explicit paths from the caller stay as they are."""
    entries = load_registry(registry_path())
    if not request.main_gguf:
        match request.tier:
            case ModelTier.LEAST_CENSORED:
                chosen = _stock_least_censored(entries, free_gb)
            case ModelTier.STANDARD:
                chosen = _stock_main(entries, free_gb)
            case _ as unreachable:
                assert_never(unreachable)
        _bind_main(request, chosen, store)
    if (
        request.dark_themes
        and request.tier is ModelTier.STANDARD
        and not request.least_censored_gguf
    ):
        _bind_least(request, _dark_pass(entries, store, free_gb), store)


def prepare_real_models(
    request: BookRequest,
    *,
    store: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """First-run stock download, then the dark-theme model choice."""
    gpu = require_supported_gpu()
    folder = store or gguf_dir()
    _say(on_progress, "Downloading the stock models that fit this GPU.")
    ensure_default_install(free_gb=gpu.free_gb, store=folder)
    assign_book_models(request, free_gb=gpu.free_gb, store=folder)


def _stock_main(entries: list[RegistryEntry], free_gb: float) -> RegistryEntry:
    for entry in entries:
        if entry.role == "main" and is_stock(entry) and fits_vram(entry, free_gb):
            return entry
    raise PlotweaverError("No stock model fits the free VRAM.")


def _stock_least_censored(entries: list[RegistryEntry], free_gb: float) -> RegistryEntry:
    stock = [
        entry
        for entry in entries
        if entry.role == "least-censored" and is_stock(entry) and fits_vram(entry, free_gb)
    ]
    for entry in stock:
        if entry.default:
            return entry
    if stock:
        return stock[0]
    raise PlotweaverError("No stock least-censored model fits the free VRAM.")


def _dark_pass(entries: list[RegistryEntry], store: Path, free_gb: float) -> RegistryEntry:
    installed = [
        entry
        for entry in entries
        if entry.enabled
        and entry.uncensored
        and fits_vram(entry, free_gb)
        and (store / entry.filename).is_file()
    ]
    if installed:
        return max(installed, key=lambda entry: entry.min_vram_gb)
    return _stock_least_censored(entries, free_gb)


def _installed(entry: RegistryEntry, store: Path) -> Path:
    path = store / entry.filename
    if not path.is_file():
        raise PlotweaverError(f"{entry.id} is not installed ({path.name}).")
    return path


def _bind_main(request: BookRequest, entry: RegistryEntry, store: Path) -> None:
    request.main_gguf = str(_installed(entry, store))
    request.main_model_id = entry.id


def _bind_least(request: BookRequest, entry: RegistryEntry, store: Path) -> None:
    request.least_censored_gguf = str(_installed(entry, store))
    request.least_censored_model_id = entry.id


def _say(on_progress: Callable[[str], None] | None, message: str) -> None:
    if callable(on_progress):
        on_progress(message)
