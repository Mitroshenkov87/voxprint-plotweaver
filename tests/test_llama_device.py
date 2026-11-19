"""Vulkan device choice prefers the NVIDIA GPU on an Optimus laptop."""

from __future__ import annotations

from plotweaver.llama_server import nvidia_device_arg


def test_nvidia_device_index_skips_the_igpu() -> None:
    listing = (
        "ggml_vulkan: 0 = Intel(R) Arc(TM) Graphics (Intel) | uma: 1\n"
        "ggml_vulkan: 1 = NVIDIA GeForce RTX 4090 Laptop GPU (NVIDIA) | uma: 0\n"
    )
    assert nvidia_device_arg(listing) == "1"


def test_missing_nvidia_device_is_unset() -> None:
    assert nvidia_device_arg("ggml_vulkan: 0 = Intel(R) UHD Graphics\n") is None
