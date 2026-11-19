"""Read the few GGUF metadata fields the VRAM planner needs.

Only the metadata block is touched. A 20 GB weight file is not loaded into memory.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

from plotweaver.errors import PlotweaverError

_UINT8, _INT8, _UINT16, _INT16, _UINT32, _INT32, _FLOAT32, _BOOL = range(8)
_STRING, _ARRAY, _UINT64, _INT64, _FLOAT64 = range(8, 13)
_SCALAR = {
    _UINT8: "<B",
    _INT8: "<b",
    _UINT16: "<H",
    _INT16: "<h",
    _UINT32: "<I",
    _INT32: "<i",
    _FLOAT32: "<f",
    _UINT64: "<Q",
    _INT64: "<q",
    _FLOAT64: "<d",
}


class GGUFError(PlotweaverError):
    """The file is not a GGUF we can plan from."""


def _read(handle: BinaryIO, size: int) -> bytes:
    blob = handle.read(size)
    if len(blob) != size:
        raise GGUFError("unexpected end of GGUF metadata")
    return blob


def _string(handle: BinaryIO) -> str:
    (length,) = struct.unpack("<Q", _read(handle, 8))
    if length > 64 * 1024 * 1024:
        raise GGUFError("GGUF string is unreasonably long")
    return _read(handle, length).decode("utf-8", errors="replace")


def _skip(handle: BinaryIO, value_type: int) -> None:
    if value_type == _BOOL:
        _read(handle, 1)
        return
    if value_type == _STRING:
        (length,) = struct.unpack("<Q", _read(handle, 8))
        _read(handle, length)
        return
    if value_type == _ARRAY:
        (item_type,) = struct.unpack("<I", _read(handle, 4))
        (count,) = struct.unpack("<Q", _read(handle, 8))
        if count > 1_000_000:
            raise GGUFError("GGUF array is unreasonably long")
        for _ in range(count):
            _skip(handle, item_type)
        return
    fmt = _SCALAR.get(value_type)
    if fmt is None:
        raise GGUFError(f"unknown GGUF type {value_type}")
    _read(handle, struct.calcsize(fmt))


def _value(handle: BinaryIO, value_type: int) -> object:
    if value_type == _STRING:
        return _string(handle)
    if value_type == _BOOL:
        return _read(handle, 1) != b"\x00"
    if value_type == _ARRAY:
        _skip(handle, value_type)
        return None
    fmt = _SCALAR.get(value_type)
    if fmt is None:
        raise GGUFError(f"unknown GGUF type {value_type}")
    (value,) = struct.unpack(fmt, _read(handle, struct.calcsize(fmt)))
    return value


def read_planner_fields(path: Path) -> dict[str, object]:
    """Architecture, block count, and expert count, when the file publishes them."""
    with path.open("rb") as handle:
        magic = _read(handle, 4)
        if magic != b"GGUF":
            raise GGUFError(f"{path} is not a GGUF file")
        (version,) = struct.unpack("<I", _read(handle, 4))
        if version < 2:
            raise GGUFError(f"GGUF version {version} is too old")
        _read(handle, 8)  # tensor count, unused
        (pairs,) = struct.unpack("<Q", _read(handle, 8))
        found: dict[str, object] = {}
        wanted = {
            "general.architecture",
            "block_count",
            "expert_count",
            "embedding_length",
        }
        for _ in range(pairs):
            key = _string(handle)
            (value_type,) = struct.unpack("<I", _read(handle, 4))
            interesting = key in wanted or any(key.endswith("." + suffix) for suffix in wanted)
            if interesting and value_type != _ARRAY:
                found[key] = _value(handle, value_type)
            else:
                _skip(handle, value_type)
        return found


def block_and_experts(path: Path) -> tuple[int, int]:
    """Best-effort (block_count, expert_count). Unknown files return (0, 0)."""
    try:
        fields = read_planner_fields(path)
    except OSError, GGUFError:
        return 0, 0
    architecture = str(fields.get("general.architecture") or "")
    block = fields.get(f"{architecture}.block_count", fields.get("block_count", 0))
    experts = fields.get(f"{architecture}.expert_count", fields.get("expert_count", 0))
    return _count(block), _count(experts)


def _count(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0
