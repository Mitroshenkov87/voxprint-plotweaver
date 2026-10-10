"""Default stock downloads, and the separate abliterated download from Settings.

The first real run detects VRAM, picks the 16 GB or 24 GB tier, and downloads
stock models that tier can run with 2 GB or 3 GB of headroom. Abliterated
models stay out of that set. Settings can download them when the GPU has at
least 20 GB and the same tier rule allows the file. A dark-theme book uses an
installed abliterated file when one fits, and otherwise the stock
least-censored model, or the stock drafter when that file does not fit.
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
    is_stock,
    load_registry,
    model_offered,
    registry_path,
    uncensored_offer_allowed,
)


def ensure_default_install(
    *, free_gb: float, total_gb: float | None = None, store: Path | None = None
) -> int:
    """Download stock models for the detected tier. Skip files already present."""
    total = free_gb if total_gb is None else total_gb
    folder = store or gguf_dir()
    count = 0
    for entry in load_registry(registry_path()):
        if not is_stock(entry) or not model_offered(entry, total_gb=total, free_gb=free_gb):
            continue
        if (folder / entry.filename).is_file():
            continue
        download_model(entry, folder)
        count += 1
    return count


def ensure_uncensored_models(
    *, total_vram_gb: float, free_gb: float | None = None, store: Path | None = None
) -> int:
    """Download abliterated models that this tier can run. Refused below 20 GB."""
    if not uncensored_offer_allowed(total_vram_gb):
        raise PlotweaverError("Abliterated models need a GPU with at least 20 GB of VRAM.")
    free = total_vram_gb if free_gb is None else free_gb
    folder = store or gguf_dir()
    count = 0
    for entry in load_registry(registry_path()):
        if not entry.enabled or not entry.uncensored:
            continue
        if not model_offered(entry, total_gb=total_vram_gb, free_gb=free):
            continue
        if (folder / entry.filename).is_file():
            continue
        download_model(entry, folder)
        count += 1
    return count


def assign_book_models(
    request: BookRequest,
    *,
    free_gb: float,
    store: Path,
    total_gb: float | None = None,
) -> None:
    """Fill empty model paths. Explicit paths from the caller stay as they are."""
    total = free_gb if total_gb is None else total_gb
    entries = load_registry(registry_path())
    if not request.main_gguf:
        match request.tier:
            case ModelTier.LEAST_CENSORED:
                chosen = _stock_least_censored(entries, total, free_gb)
            case ModelTier.STANDARD:
                chosen = _stock_main(entries, total, free_gb)
            case _ as unreachable:
                assert_never(unreachable)
        _bind_main(request, chosen, store)
    if (
        request.dark_themes
        and request.tier is ModelTier.STANDARD
        and not request.least_censored_gguf
    ):
        _bind_least(request, _dark_pass(entries, store, total, free_gb), store)


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
    ensure_default_install(free_gb=gpu.free_gb, total_gb=gpu.total_gb, store=folder)
    assign_book_models(request, free_gb=gpu.free_gb, total_gb=gpu.total_gb, store=folder)


def _offered(entry: RegistryEntry, total_gb: float, free_gb: float) -> bool:
    return model_offered(entry, total_gb=total_gb, free_gb=free_gb)


def _stock_main(entries: list[RegistryEntry], total_gb: float, free_gb: float) -> RegistryEntry:
    for entry in entries:
        if entry.role == "main" and is_stock(entry) and _offered(entry, total_gb, free_gb):
            return entry
    raise PlotweaverError("No stock model fits this VRAM tier.")


def _stock_least_censored(
    entries: list[RegistryEntry], total_gb: float, free_gb: float
) -> RegistryEntry:
    stock = [
        entry
        for entry in entries
        if entry.role == "least-censored" and is_stock(entry) and _offered(entry, total_gb, free_gb)
    ]
    for entry in stock:
        if entry.default:
            return entry
    if stock:
        return stock[0]
    return _stock_main(entries, total_gb, free_gb)


def _dark_pass(
    entries: list[RegistryEntry], store: Path, total_gb: float, free_gb: float
) -> RegistryEntry:
    installed = [
        entry
        for entry in entries
        if entry.enabled
        and entry.uncensored
        and _offered(entry, total_gb, free_gb)
        and (store / entry.filename).is_file()
    ]
    if installed:
        return max(installed, key=lambda entry: entry.min_vram_gb)
    return _stock_least_censored(entries, total_gb, free_gb)


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
