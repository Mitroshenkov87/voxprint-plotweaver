"""Default stock downloads, and the separate least-censored download from Settings.

The installer downloads the stock models for the detected tier. A later launch
only repairs a file that is missing or corrupt. Least-censored models come
from Model Forge and stay out of that set until Settings asks for them. A
Russian book prefers the forge T-lite file when it is installed. Otherwise
the largest installed forge model for the tier is used, and the stock drafter
is the fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import assert_never

from plotweaver.domain import BookRequest, Language, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.fetch import estimate_minutes, format_size
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
from plotweaver.ui.i18n import tr


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


def optional_notice(entry: RegistryEntry) -> str:
    """Size and a rough time estimate for one optional download."""
    return tr("optional_notice").format(
        name=entry.filename,
        size=format_size(entry.size),
        minutes=estimate_minutes(entry.size),
    )


def ensure_uncensored_models(
    *,
    total_vram_gb: float,
    free_gb: float | None = None,
    store: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> int:
    """Download published least-censored models that this tier can run."""
    free = total_vram_gb if free_gb is None else free_gb
    if not uncensored_offer_allowed(total_vram_gb, free):
        raise PlotweaverError("No published least-censored model fits this card.")
    folder = store or gguf_dir()
    count = 0
    for entry in load_registry(registry_path()):
        if not entry.enabled or not entry.uncensored:
            continue
        if not model_offered(entry, total_gb=total_vram_gb, free_gb=free):
            continue
        if (folder / entry.filename).is_file():
            continue
        _say(on_progress, optional_notice(entry))
        download_model(entry, folder, on_progress=on_progress)
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
                chosen = _least_censored(entries, total, free_gb, store, request.language)
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
        _bind_least(
            request,
            _least_censored(entries, total, free_gb, store, request.language),
            store,
        )


def prepare_real_models(
    request: BookRequest,
    *,
    store: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """First-run stock download, then the dark-theme model choice."""
    gpu = require_supported_gpu()
    folder = store or gguf_dir()
    _say(on_progress, tr("repair_checking"))
    ensure_default_install(free_gb=gpu.free_gb, total_gb=gpu.total_gb, store=folder)
    assign_book_models(request, free_gb=gpu.free_gb, total_gb=gpu.total_gb, store=folder)


def _offered(entry: RegistryEntry, total_gb: float, free_gb: float) -> bool:
    return model_offered(entry, total_gb=total_gb, free_gb=free_gb)


def _stock_main(entries: list[RegistryEntry], total_gb: float, free_gb: float) -> RegistryEntry:
    for entry in entries:
        if entry.role == "main" and is_stock(entry) and _offered(entry, total_gb, free_gb):
            return entry
    raise PlotweaverError("No stock model fits this VRAM tier.")


def _least_censored(
    entries: list[RegistryEntry],
    total_gb: float,
    free_gb: float,
    store: Path,
    language: Language,
) -> RegistryEntry:
    """Installed Model Forge model for this language and tier, else the stock drafter."""
    installed = [
        entry
        for entry in entries
        if entry.enabled
        and entry.uncensored
        and entry.role == "least-censored"
        and _offered(entry, total_gb, free_gb)
        and (store / entry.filename).is_file()
    ]
    specific = [entry for entry in installed if language.value in entry.languages]
    if specific:
        return _preferred(specific)
    general = [entry for entry in installed if not entry.languages]
    if general:
        return _preferred(general)
    return _stock_main(entries, total_gb, free_gb)


def _preferred(entries: list[RegistryEntry]) -> RegistryEntry:
    marked = [entry for entry in entries if entry.default]
    pool = marked or entries
    return max(pool, key=lambda entry: entry.min_vram_gb)


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
