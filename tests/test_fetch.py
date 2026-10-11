"""Disk check and partial-file cleanup for model downloads."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from plotweaver.errors import PlotweaverError
from plotweaver.runtime_fetch import stream_download


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
    monkeypatch.setattr("plotweaver.runtime_fetch.shutil.disk_usage", lambda _path: _Usage(1024))
    dest = tmp_path / "model.gguf"
    with pytest.raises(PlotweaverError, match="Not enough disk space") as caught:
        stream_download(
            "http://127.0.0.1/model.gguf",
            dest,
            total=2_000_000_000,
            on_progress=None,
            label="model.gguf",
            sha256="ab" * 32,
        )
    message = str(caught.value)
    assert f"Not enough disk space on {dest.anchor}" in message
    assert "Need" in message
    assert "GB free" in message
    assert not dest.exists()
    assert not dest.with_suffix(".gguf.partial").exists()


def test_empty_partial_is_removed_and_a_partial_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "model.gguf"
    partial = dest.with_suffix(".gguf.partial")
    partial.write_bytes(b"abc")
    calls: list[dict[str, str]] = []

    def fail_then_resume(method: str, url: str, **kwargs: object) -> _Response:
        del method, url
        headers = kwargs.get("headers")
        assert isinstance(headers, dict)
        calls.append({str(key): str(value) for key, value in headers.items()})
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return _Response(206, [b"def"])

    monkeypatch.setattr("plotweaver.runtime_fetch.httpx.stream", fail_then_resume)
    monkeypatch.setattr("plotweaver.runtime_fetch.time.sleep", lambda _seconds: None)
    stream_download(
        "http://127.0.0.1/x",
        dest,
        total=6,
        on_progress=None,
        label="x",
        sha256="bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721",
    )
    assert dest.read_bytes() == b"abcdef"
    assert calls[0].get("Range") == "bytes=3-"
    assert calls[1]["Range"] == "bytes=3-"
    assert not partial.exists()


def test_download_retries_ten_times_and_keeps_a_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "model.gguf"
    partial = dest.with_suffix(".gguf.partial")
    partial.write_bytes(b"abc")
    calls = {"n": 0}

    def always_down(method: str, url: str, **kwargs: object) -> _Response:
        del method, url, kwargs
        calls["n"] += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr("plotweaver.runtime_fetch.httpx.stream", always_down)
    monkeypatch.setattr("plotweaver.runtime_fetch.time.sleep", lambda _seconds: None)
    with pytest.raises(PlotweaverError, match="Could not download"):
        stream_download(
            "http://127.0.0.1/x",
            dest,
            total=6,
            on_progress=None,
            label="x",
            sha256="ab" * 32,
        )
    assert calls["n"] == 10
    assert partial.read_bytes() == b"abc"
    assert not dest.exists()


def test_download_refuses_a_model_without_a_sha256(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "nested" / "model.gguf"
    partial = dest.with_suffix(".gguf.partial")

    def fail_if_called(method: str, url: str, **kwargs: object) -> _Response:
        del method, url, kwargs
        raise AssertionError("download started")

    monkeypatch.setattr("plotweaver.runtime_fetch.httpx.stream", fail_if_called)
    for digest in ("", "abc", "AB" * 31):
        with pytest.raises(PlotweaverError, match="no SHA-256"):
            stream_download(
                "http://127.0.0.1/x",
                dest,
                total=6,
                on_progress=None,
                label="model.gguf",
                sha256=digest,
            )
    assert not dest.exists()
    assert not partial.exists()
    assert not dest.parent.exists()
