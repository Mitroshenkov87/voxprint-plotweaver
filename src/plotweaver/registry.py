"""Model registry, shared GGUF folder, and SHA-256 checks.

Weights live in ``<shared>/models/llm``. A matching file already stored under
the older ``<home>/models/llm`` path is reused. Every entry records a confirmed
base licence. Apache-2.0 and MIT are accepted. An empty licence is refused,
including with --allow-other-license, because an untagged tune has nothing to
record. Heretic is not a registry entry.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

from voxprint_common.gpu_probe import TIER_24_MIN_GIB, VramTier, tier_for_gib
from voxprint_common.hashing import sha256_file

from plotweaver.atomic import write_json
from plotweaver.errors import PlotweaverError
from plotweaver.fetch import stream_download
from plotweaver.paths import gguf_dir, legacy_models_dir, repo_root
from plotweaver.settings import model_tier_override
from plotweaver.textio import read_text

APPROVED_LICENSES = {"apache-2.0", "mit"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BARE_QUANT = re.compile(r"^(?:IQ|Q)[A-Z0-9_]*\.gguf$")
TIER_16: Literal["16gb"] = "16gb"
TIER_24: Literal["24gb"] = "24gb"
# A 4090 reports 24564 MiB, which is 23.99 GiB. The suite probe's 24 GB cut is 23.5 GiB.
TIER_24_MIN_GB = float(TIER_24_MIN_GIB)
TierName = Literal["16gb", "24gb"]
TierOverride = Literal["auto", "16gb", "24gb"]


@dataclass(frozen=True)
class RegistryEntry:
    """One published model row from the registry file."""

    id: str
    role: str
    repo: str
    filename: str
    sha256: str
    size: int
    license: str
    min_vram_gb: float
    context: int
    moe: bool
    notes: str
    revision: str = ""
    base_repo: str = ""
    base_revision: str = ""
    base_license: str = ""
    card: str = ""
    tier: str = ""
    default: bool = False
    enabled: bool = True
    optional: bool = False
    uncensored: bool = False
    languages: tuple[str, ...] = ()


def load_registry(path: Path) -> list[RegistryEntry]:
    """Read the model rows from a registry TOML file."""
    payload = tomllib.loads(read_text(path))
    rows = payload.get("model") or []
    if not isinstance(rows, list):
        raise PlotweaverError(f"{path} has no [[model]] entries")
    entries: list[RegistryEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = RegistryEntry(
            id=str(row["id"]),
            role=str(row.get("role") or "main"),
            repo=str(row["repo"]),
            filename=str(row["filename"]),
            sha256=str(row["sha256"]).lower(),
            size=int(row["size"]),
            license=str(row.get("license") or ""),
            min_vram_gb=float(row.get("min_vram_gb") or 0),
            context=int(row.get("context") or 8192),
            moe=bool(row.get("moe")),
            notes=str(row.get("notes") or ""),
            revision=str(row.get("revision") or ""),
            base_repo=str(row.get("base_repo") or ""),
            base_revision=str(row.get("base_revision") or ""),
            base_license=str(row.get("base_license") or ""),
            card=str(row.get("card") or ""),
            tier=str(row.get("tier") or row.get("card") or ""),
            default=bool(row.get("default")),
            enabled=bool(row.get("enabled", True)),
            optional=bool(row.get("optional")),
            uncensored=bool(row.get("uncensored")),
            languages=_languages(row),
        )
        if entry.enabled and (
            not entry.revision
            or not entry.sha256
            or entry.size <= 0
            or not entry.base_repo
            or not entry.base_license
        ):
            raise PlotweaverError(
                f"{entry.id} needs revision, sha256, size, base_repo, and base_license. "
                "Untagged tunes are not downloaded."
            )
        if entry.tier not in {TIER_16, TIER_24}:
            raise PlotweaverError(f"{entry.id} needs tier {TIER_16} or {TIER_24}")
        entries.append(entry)
    return entries


def _languages(row: dict[str, object]) -> tuple[str, ...]:
    raw = row.get("languages") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise PlotweaverError("languages must be a list of language codes")
    found: list[str] = []
    for item in raw:
        text = str(item).strip().lower()
        if text:
            found.append(text)
    return tuple(found)


def licence_allowed(entry: RegistryEntry, *, allow_other: bool = False) -> bool:
    return _licence_ok(entry.license, allow_other=allow_other) and _licence_ok(
        entry.base_license, allow_other=allow_other
    )


def _licence_ok(value: str, *, allow_other: bool) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    if text in APPROVED_LICENSES:
        return True
    return allow_other


def canonical_licence(value: str) -> str:
    text = value.strip().lower()
    if text == "apache-2.0":
        return "Apache-2.0"
    if text == "mit":
        return "MIT"
    return value.strip()


def verify_file(path: Path, *, size: int, sha256: str) -> None:
    actual = path.stat().st_size
    if actual != size:
        raise PlotweaverError(f"{path.name} is {actual} bytes, expected {size}")
    found = sha256_file(path)
    if found != sha256.lower():
        raise PlotweaverError(f"{path.name} SHA-256 {found} does not match {sha256}")


def claim_user(store: Path, user: str = "plotweaver") -> None:
    """Add this app to `<models>/.users.json` without dropping other suite apps.

    The file is the same one Audiobook Builder and Movie Dubber share. A key that
    is already true is left byte-for-byte alone.
    """
    store.mkdir(parents=True, exist_ok=True)
    path = store / ".users.json"
    data: dict[str, bool] = {}
    if path.is_file():
        try:
            loaded = json.loads(read_text(path))
        except UnicodeError, json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            data = {str(key): bool(value) for key, value in loaded.items()}
    if data.get(user) is True:
        return
    data[user] = True
    payload = json.dumps(data, indent=1, sort_keys=True)
    tmp = path.with_name(f".users.json.{os.urandom(4).hex()}.tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def registry_path() -> Path:
    """Path to the bundled bakeoff/models.toml registry."""
    return repo_root() / "bakeoff" / "models.toml"


def is_stock(entry: RegistryEntry) -> bool:
    """Stock models are the default install. Abliterated rows are optional."""
    return entry.enabled and not entry.optional and not entry.uncensored


def stock_for_tier(entries: list[RegistryEntry], *, total_gb: float) -> list[RegistryEntry]:
    """Stock models for the detected tier only. A 24 GB card does not also take 16 GB files."""
    selected = resolve_tier(total_gb)
    return [entry for entry in entries if is_stock(entry) and entry_tier(entry) == selected]


def fits_vram(entry: RegistryEntry, free_gb: float) -> bool:
    """Bake-off gate: the file fits free VRAM. The app uses model_offered instead."""
    return entry.min_vram_gb <= free_gb + 0.5


def entry_tier(entry: RegistryEntry) -> str:
    return entry.tier or entry.card


def tier_headroom_gb(total_gb: float) -> float:
    """Leave 2 GB free below 23.5 GB, and 3 GB free on a 24 GB card or larger."""
    if total_gb >= TIER_24_MIN_GB:
        return 3.0
    return 2.0


def usable_vram_gb(total_gb: float, free_gb: float) -> float:
    return max(0.0, min(free_gb, total_gb - tier_headroom_gb(total_gb)))


def tier_capacity_gb(total_gb: float) -> float:
    """VRAM available for choosing models, from the card total, ignoring other processes."""
    return max(0.0, total_gb - tier_headroom_gb(total_gb))


def detected_tier(total_gb: float) -> TierName:
    """24 GB at the suite probe's 23.5 GiB cut. 8 GB and 16 GB stay on the 16 GB plan."""
    found = tier_for_gib(total_gb)
    if found is VramTier.GB24:
        return TIER_24
    if found is VramTier.GB16 or found is VramTier.GB8 or found is VramTier.UNKNOWN:
        return TIER_16
    assert_never(found)


def _normalise_override(value: str) -> TierOverride:
    match value:
        case "auto":
            return "auto"
        case "16gb":
            return TIER_16
        case "24gb":
            return TIER_24
        case _:
            return "auto"


def resolve_tier(total_gb: float, override: str | None = None) -> TierName:
    """Auto picks 16 GB under 23.5 GB of VRAM, and 24 GB at that size or above.

    A saved 24 GB override on a smaller card falls back to the detected tier.
    """
    raw = model_tier_override() if override is None else override
    choice = _normalise_override(raw)
    match choice:
        case "auto":
            return detected_tier(total_gb)
        case "16gb":
            return TIER_16
        case "24gb":
            if total_gb >= TIER_24_MIN_GB:
                return TIER_24
            return detected_tier(total_gb)
        case _ as unreachable:
            assert_never(unreachable)


def _tier_rank(tier: str) -> int:
    match tier:
        case "16gb":
            return 16
        case "24gb":
            return 24
        case _:
            return 0


def tier_allows(entry: RegistryEntry, selected: str) -> bool:
    """A 24 GB card can still run 16 GB models. A 16 GB card cannot run 24 GB models."""
    rank = _tier_rank(entry_tier(entry))
    selected_rank = _tier_rank(selected)
    if rank == 0 or selected_rank == 0:
        return False
    return rank <= selected_rank


def model_offered(
    entry: RegistryEntry,
    *,
    total_gb: float,
    free_gb: float,
    override: str | None = None,
) -> bool:
    """True when this card's total VRAM tier can run the file.

    ``free_gb`` is accepted so callers can pass the live reading. The install
    set follows the card total, not memory another process is holding.
    """
    del free_gb
    if not tier_allows(entry, resolve_tier(total_gb, override)):
        return False
    return entry.min_vram_gb <= tier_capacity_gb(total_gb)


def tier_option_enabled(tier: str, *, total_gb: float, free_gb: float) -> bool:
    """Settings can force 24 GB only when some published 24 GB model fits the card total."""
    del free_gb
    choice = _normalise_override(tier)
    match choice:
        case "auto" | "16gb":
            return True
        case "24gb":
            if total_gb < TIER_24_MIN_GB:
                return False
            usable = tier_capacity_gb(total_gb)
            try:
                entries = load_registry(registry_path())
            except PlotweaverError:
                return False
            return any(
                item.enabled and entry_tier(item) == TIER_24 and item.min_vram_gb <= usable
                for item in entries
            )
        case _ as unreachable:
            assert_never(unreachable)


def uncensored_offer_allowed(total_vram_gb: float | None, free_gb: float | None = None) -> bool:
    """True when this card can run a published least-censored model."""
    if total_vram_gb is None:
        return False
    free = total_vram_gb if free_gb is None else free_gb
    return any(
        entry.enabled
        and entry.uncensored
        and model_offered(entry, total_gb=total_vram_gb, free_gb=free)
        for entry in load_registry(registry_path())
    )


def bakeoff_skip_reason(entry: RegistryEntry, *, free_gb: float) -> str | None:
    """The bake-off downloads every enabled candidate that fits, stock or abliterated."""
    if not entry.enabled:
        return "disabled until the file is published with a revision and SHA-256"
    if not fits_vram(entry, free_gb):
        return f"needs {entry.min_vram_gb} GB, {free_gb:.1f} GB free"
    return None


def stored_filename(entry: RegistryEntry) -> str:
    """On-disk GGUF name. A bare quant such as ``Q5_K_M.gguf`` is prefixed with the model id."""
    if _BARE_QUANT.fullmatch(entry.filename):
        return f"{entry.id}-{entry.filename}"
    return entry.filename


def migrate_generic_weight(folder: Path, entry: RegistryEntry) -> Path | None:
    """Hardlink a verified generic quant onto the model-id name, then remove the generic name.

    A file whose SHA-256 does not match is left in place. A legacy copy outside
    ``folder`` is not touched.
    """
    stored_name = stored_filename(entry)
    stored = folder / stored_name
    if stored.is_file():
        return stored
    if stored_name == entry.filename:
        return None
    generic = folder / entry.filename
    if not generic.is_file():
        return None
    try:
        verify_file(generic, size=entry.size, sha256=entry.sha256)
    except PlotweaverError, OSError:
        return None
    stored.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(generic, stored)
    except OSError:
        shutil.copy2(generic, stored)
    try:
        verify_file(stored, size=entry.size, sha256=entry.sha256)
    except PlotweaverError, OSError:
        stored.unlink(missing_ok=True)
        return None
    if generic.resolve() != stored.resolve():
        generic.unlink()
    return stored


def weight_path(folder: Path, entry: RegistryEntry) -> Path:
    """Installed weight, after a verified generic quant has been renamed by hardlink."""
    migrated = migrate_generic_weight(folder, entry)
    if migrated is not None and migrated.is_file():
        return migrated
    return folder / stored_filename(entry)


def download_model(
    entry: RegistryEntry,
    store: Path | None = None,
    *,
    allow_other: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Download one enabled registry file into the shared model folder and check it."""
    if not entry.enabled:
        raise PlotweaverError(
            f"{entry.id} is disabled until Voxprint Model Forge publishes it "
            "with a revision and SHA-256. Plotweaver does not abliterate or quantize."
        )
    if not licence_allowed(entry, allow_other=allow_other):
        raise PlotweaverError(
            f"{entry.id} is licensed {entry.license!r} "
            f"(base {entry.base_license!r}). "
            "Plotweaver downloads Apache-2.0 and MIT weights with a confirmed "
            "base licence unless you pass --allow-other-license. "
            "An empty licence is refused."
        )
    folder = store or gguf_dir()
    folder.mkdir(parents=True, exist_ok=True)
    claim_user(folder.parent)
    legacy = legacy_models_dir()
    if legacy.resolve() != folder.parent.resolve():
        claim_user(legacy)
    local_name = stored_filename(entry)
    target = folder / local_name
    migrate_generic_weight(folder, entry)
    url = (
        f"https://huggingface.co/{entry.repo}/resolve/{entry.revision}/"
        f"{entry.filename}?download=true"
    )
    if target.is_file():
        try:
            verify_file(target, size=entry.size, sha256=entry.sha256)
        except PlotweaverError:
            target.unlink()
    if not target.is_file():
        stream_download(
            url,
            target,
            total=entry.size,
            on_progress=on_progress,
            label=local_name,
            sha256=entry.sha256,
        )
    verify_file(target, size=entry.size, sha256=entry.sha256)
    manifest = {
        "id": entry.id,
        "repo": entry.repo,
        "revision": entry.revision,
        "files": [{"path": local_name, "sha256": entry.sha256, "size": entry.size}],
        "license": canonical_licence(entry.license),
        "base_repo": entry.base_repo,
        "base_revision": entry.base_revision,
        "base_license": canonical_licence(entry.base_license),
        "role": entry.role,
        "card": entry.card,
        "tier": entry_tier(entry),
        "default": entry.default,
        "notes": entry.notes,
    }
    write_json(folder / f"{entry.id}.manifest.json", manifest)
    return target


def model_public_row(entry: RegistryEntry) -> dict[str, object]:
    """Fields a bot can rely on from `plotweaver models list --json`."""
    return {
        "id": entry.id,
        "enabled": entry.enabled,
        "tier": entry.tier,
        "role": entry.role,
        "filename": entry.filename,
        "repo": entry.repo,
        "revision": entry.revision,
        "sha256": entry.sha256,
        "size": entry.size,
        "license": entry.license,
        "min_vram_gb": entry.min_vram_gb,
        "uncensored": entry.uncensored,
        "optional": entry.optional,
        "default": entry.default,
        "languages": list(entry.languages),
    }


def import_forge_manifest(
    manifest: Path,
    registry: Path | None = None,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Fill disabled least-censored rows from a Model Forge JSON manifest.

    Each object needs ``id``, ``revision``, ``sha256``, and ``size``. Optional
    ``repo``, ``filename``, and ``min_vram_gb`` replace those fields. The row
    is enabled. Stock rows are refused. ``dry_run`` validates and returns the
    ids without writing the registry.
    """
    path = registry or registry_path()
    payload = json.loads(read_text(manifest))
    if not isinstance(payload, dict):
        raise PlotweaverError("forge manifest must be a JSON object")
    rows = payload.get("models")
    if not isinstance(rows, list) or not rows:
        raise PlotweaverError("forge manifest needs a non-empty models list")
    known = {entry.id: entry for entry in load_registry(path)}
    text = read_text(path)
    enabled: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PlotweaverError("each forge manifest model must be an object")
        model_id = str(row.get("id") or "")
        entry = known.get(model_id)
        if entry is None:
            raise PlotweaverError(f"{model_id} is not in the registry")
        if is_stock(entry):
            raise PlotweaverError(f"{model_id} is a stock model. Model Forge cannot replace it.")
        text = _fill_registry_block(text, model_id, _forge_updates(row))
        enabled.append(model_id)
    if dry_run:
        return enabled
    _write_registry(path, text)
    loaded = {entry.id: entry for entry in load_registry(path)}
    for model_id in enabled:
        filled = loaded[model_id]
        if not filled.enabled or not filled.revision or not filled.sha256 or filled.size <= 0:
            raise PlotweaverError(f"{model_id} was not enabled")
    return enabled


def _forge_updates(row: dict[str, object]) -> dict[str, str]:
    revision = _forge_text(row, "revision")
    digest = _forge_text(row, "sha256").lower()
    if _SHA256.fullmatch(digest) is None:
        raise PlotweaverError("forge manifest sha256 must be 64 hex characters")
    size = row.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise PlotweaverError("forge manifest size must be a positive integer")
    updates = {
        "revision": _toml_string(revision),
        "sha256": _toml_string(digest),
        "size": str(size),
        "enabled": "true",
    }
    if "repo" in row:
        updates["repo"] = _toml_string(_forge_text(row, "repo"))
    if "filename" in row:
        updates["filename"] = _toml_string(_forge_text(row, "filename"))
    if "min_vram_gb" in row:
        raw = row["min_vram_gb"]
        if isinstance(raw, bool) or not isinstance(raw, int | float) or float(raw) <= 0:
            raise PlotweaverError("forge manifest min_vram_gb must be a positive number")
        updates["min_vram_gb"] = _toml_number(float(raw))
    return updates


def _forge_text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlotweaverError(f"forge manifest {key} must be a non-empty string")
    return value.strip()


def _toml_string(value: str) -> str:
    if any(character in value for character in ('"', "\\", "\n", "\r")):
        raise PlotweaverError("forge manifest strings cannot contain quotes or line breaks")
    return f'"{value}"'


def _toml_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _fill_registry_block(text: str, model_id: str, updates: dict[str, str]) -> str:
    marker = f'id = "{model_id}"'
    start = text.find(marker)
    if start < 0:
        raise PlotweaverError(f"{model_id} is not in the registry file")
    block_start = text.rfind("[[model]]", 0, start)
    if block_start < 0:
        raise PlotweaverError(f"{model_id} is not inside a model block")
    next_at = text.find("\n[[model]]", start)
    if next_at < 0:
        block = text[block_start:]
        rest = ""
    else:
        block = text[block_start:next_at]
        rest = text[next_at:]
    for key, rendered in updates.items():
        block = _set_toml_field(block, key, rendered)
    if rest and not block.endswith("\n"):
        block += "\n"
    return text[:block_start] + block + rest


def _set_toml_field(block: str, key: str, rendered: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)} = .*$", re.MULTILINE)
    line = f"{key} = {rendered}"
    if pattern.search(block):
        return pattern.sub(line, block, count=1)
    if not block.endswith("\n"):
        block += "\n"
    return block + line + "\n"


def _write_registry(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.urandom(4).hex()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
