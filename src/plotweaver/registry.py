"""Model registry, shared GGUF folder, and SHA-256 checks.

Weights live in `<models>/llm` (the suite folder Audiobook Builder uses).
Every entry records a confirmed base licence. Apache-2.0 and MIT are accepted.
An empty licence is refused, including with --allow-other-license, because an
untagged tune has nothing to record. Heretic is not a registry entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

import httpx

from plotweaver.atomic import write_json
from plotweaver.errors import PlotweaverError
from plotweaver.paths import gguf_dir, repo_root
from plotweaver.settings import model_tier_override

APPROVED_LICENSES = {"apache-2.0", "mit"}
# Abliterated models are offered in Settings only on a GPU at least this large.
UNCENSORED_MIN_VRAM_GB = 20.0
TIER_16: Literal["16gb"] = "16gb"
TIER_24: Literal["24gb"] = "24gb"
TierName = Literal["16gb", "24gb"]
TierOverride = Literal["auto", "16gb", "24gb"]


@dataclass(frozen=True)
class RegistryEntry:
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


def load_registry(path: Path) -> list[RegistryEntry]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    found = digest.hexdigest()
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
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
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
    return repo_root() / "bakeoff" / "models.toml"


def is_stock(entry: RegistryEntry) -> bool:
    """Stock models are the default install. Abliterated rows are optional."""
    return entry.enabled and not entry.optional and not entry.uncensored


def fits_vram(entry: RegistryEntry, free_gb: float) -> bool:
    """Bake-off gate: the file fits free VRAM. The app uses model_offered instead."""
    return entry.min_vram_gb <= free_gb + 0.5


def entry_tier(entry: RegistryEntry) -> str:
    return entry.tier or entry.card


def tier_headroom_gb(total_gb: float) -> float:
    """Leave 2 GB free below 24 GB, and 3 GB free on a 24 GB card or larger."""
    if total_gb >= 24:
        return 3.0
    return 2.0


def usable_vram_gb(total_gb: float, free_gb: float) -> float:
    return max(0.0, min(free_gb, total_gb - tier_headroom_gb(total_gb)))


def detected_tier(total_gb: float) -> TierName:
    if total_gb >= 24:
        return TIER_24
    return TIER_16


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
    """Auto picks 16 GB under 24 GB of VRAM, and 24 GB at that size or above.

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
            if total_gb >= 24:
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
    """True when this card's tier and headroom can run the file."""
    if not tier_allows(entry, resolve_tier(total_gb, override)):
        return False
    return entry.min_vram_gb <= usable_vram_gb(total_gb, free_gb)


def tier_option_enabled(tier: str, *, total_gb: float, free_gb: float) -> bool:
    """Settings can force 24 GB only when some published 24 GB model fits."""
    choice = _normalise_override(tier)
    match choice:
        case "auto" | "16gb":
            return True
        case "24gb":
            if total_gb < 24:
                return False
            usable = usable_vram_gb(total_gb, free_gb)
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


def uncensored_offer_allowed(total_vram_gb: float | None) -> bool:
    """Settings offers abliterated models only on a 20 GB GPU or larger."""
    return total_vram_gb is not None and total_vram_gb >= UNCENSORED_MIN_VRAM_GB


def bakeoff_skip_reason(entry: RegistryEntry, *, free_gb: float) -> str | None:
    """The bake-off downloads every enabled candidate that fits, stock or abliterated."""
    if not entry.enabled:
        return "disabled until the file is published with a revision and SHA-256"
    if not fits_vram(entry, free_gb):
        return f"needs {entry.min_vram_gb} GB, {free_gb:.1f} GB free"
    return None


def download_model(
    entry: RegistryEntry, store: Path | None = None, *, allow_other: bool = False
) -> Path:
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
    target = folder / entry.filename
    url = (
        f"https://huggingface.co/{entry.repo}/resolve/{entry.revision}/"
        f"{entry.filename}?download=true"
    )
    if not target.is_file():
        partial = target.with_suffix(target.suffix + ".partial")
        headers = {"User-Agent": "plotweaver"}
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(3600.0, connect=30.0),
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
        partial.replace(target)
    verify_file(target, size=entry.size, sha256=entry.sha256)
    manifest = {
        "id": entry.id,
        "repo": entry.repo,
        "revision": entry.revision,
        "files": [{"path": entry.filename, "sha256": entry.sha256, "size": entry.size}],
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
