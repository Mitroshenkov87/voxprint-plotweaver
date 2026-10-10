"""Yo, stress, overlap, a tiny GGUF, and the llama.cpp asset picker."""

from __future__ import annotations

import struct
from pathlib import Path

from plotweaver.gguf import block_and_experts
from plotweaver.llama_release import cuda_major_from_smi, select_asset
from plotweaver.references import compare_texts
from plotweaver.registry import RegistryEntry, licence_allowed
from plotweaver.textutil import prepare_prose, restore_yo


def test_yo_dictionary_skips_vse() -> None:
    restored = restore_yo("Еще рано, все на месте, ее нет.")
    assert "Ещё" in restored
    assert "её" in restored
    assert "все" in restored
    assert "всё" not in restored
    assert "всё" not in restore_yo("все")


def test_stress_from_the_bible_skips_a_word_that_already_has_it() -> None:
    stressed = prepare_prose("Илья смотрит.", [("Илья", "Илья\u0301")])
    assert "Илья\u0301" in stressed
    again = prepare_prose(stressed, [("Илья", "Илья\u0301")])
    assert again.count("\u0301") == stressed.count("\u0301")


def test_overlap_flags_a_twelve_lemma_run_and_a_repeated_name() -> None:
    sentence = "north wind and the quiet river keep the old stone bridge"
    shared = " ".join([sentence, sentence])
    report = compare_texts(shared, shared)
    assert report.flagged
    assert any(hit.kind == "run-12" for hit in report.hits)
    names = compare_texts("Воронов вышел на пирс.", "Воронов видел Воронов на пирсе и молчал.")
    assert any(hit.kind == "name" and hit.excerpt == "Воронов" for hit in names.hits)


def test_tiny_gguf_reports_blocks(tmp_path: Path) -> None:
    def gguf_string(text: str) -> bytes:
        raw = text.encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw

    blob = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 2)
    blob += gguf_string("general.architecture") + struct.pack("<I", 8) + gguf_string("llama")
    blob += gguf_string("llama.block_count") + struct.pack("<I", 4) + struct.pack("<I", 32)
    path = tmp_path / "tiny.gguf"
    path.write_bytes(blob)
    assert block_and_experts(path) == (32, 0)


def test_cuda_asset_picker() -> None:
    names = [
        "llama-b1-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "llama-b1-bin-ubuntu-cuda-13.4-x64.tar.gz",
        "cudart-llama-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "llama-b1-bin-win-cuda-12.4-x64.zip",
    ]
    assert (
        select_asset(names, system="linux", cuda_major=12)
        == "llama-b1-bin-ubuntu-cuda-12.8-x64.tar.gz"
    )
    assert (
        select_asset(names, system="linux", cuda_major=13)
        == "llama-b1-bin-ubuntu-cuda-13.4-x64.tar.gz"
    )
    assert cuda_major_from_smi("CUDA Version: 13.0") == 13
    entry = RegistryEntry(
        id="x",
        role="main",
        repo="someone/model",
        filename="a.gguf",
        sha256="abc",
        size=1,
        license="gemma",
        min_vram_gb=1,
        context=8192,
        moe=False,
        notes="",
    )
    assert not licence_allowed(entry)
    assert licence_allowed(entry, allow_other=True)
