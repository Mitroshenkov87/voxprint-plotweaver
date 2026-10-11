"""Disk check and partial-file cleanup for model downloads."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from plotweaver.errors import PlotweaverError
from plotweaver.fetch import stream_download


class _Usage:
    def __init__(self, free: int) -> None:
        self.total = free + 1
        self.used = 1
        self.free = free


class _Response:
    def __init__(
        self, status: int, chunks: list[bytes], headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError("status")

    def iter_bytes(self, _size: int) -> object:
        yield from self._chunks


def test_disk_short_names_drive_and_sizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plotweaver.fetch.shutil.disk_usage", lambda _path: _Usage(1024))
    dest = tmp_path / "model.gguf"
    with pytest.raises(PlotweaverError, match="Not enough disk space on /") as caught:
        stream_download(
            "http://127.0.0.1/model.gguf",
            dest,
            total=2_000_000_000,
            on_progress=None,
            label="model.gguf",
        )
    assert "GB free" in str(caught.value)
    assert "Need" in str(caught.value)
    assert not dest.exists()
    assert not dest.with_suffix(".gguf.partial").exists()


def test_empty_partial_is_removed_and_a_partial_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "model.gguf"
    empty = dest.with_suffix(".gguf.partial")
    empty.write_bytes(b"")
    calls: list[dict[str, str]] = []

    def fail_then_resume(method: str, url: str, **kwargs: object) -> _Response:
        del method, url
        headers = kwargs.get("headers")
        assert isinstance(headers, dict)
        calls.append({str(key): str(value) for key, value in headers.items()})
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return _Response(206, [b"def"])

    monkeypatch.setattr("plotweaver.fetch.httpx.stream", fail_then_resume)
    with pytest.raises(PlotweaverError, match="Could not download"):
        stream_download("http://127.0.0.1/x", dest, total=6, on_progress=None, label="x")
    assert not empty.exists()
    kept = dest.with_suffix(".gguf.partial")
    kept.write_bytes(b"abc")
    stream_download("http://127.0.0.1/x", dest, total=6, on_progress=None, label="x")
    assert dest.read_bytes() == b"abcdef"
    assert calls[1]["Range"] == "bytes=3-"
    assert not kept.exists()
