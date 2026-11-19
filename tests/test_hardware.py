"""VRAM budget, GPU gate, and the 83 C thermal rule."""

from __future__ import annotations

from plotweaver.cli import main
from plotweaver.errors import GpuUnsupported
from plotweaver.hardware import (
    FULL_SPEED_S,
    HOT_C,
    GpuSample,
    ThermalGuard,
    is_supported,
    query_gpu,
    require_supported_gpu,
    vram_budget_gb,
)
from plotweaver.vram_plan import plan_server


def test_budget_is_free_minus_headroom() -> None:
    assert vram_budget_gb(22.0, 24.0) == 20.0
    # 8 percent of a 48 GB card is larger than the 2 GB floor.
    assert vram_budget_gb(40.0, 48.0) == 40.0 - 48.0 * 0.08


def test_rtx_40_is_required(monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 3060,8.6,8192,7000")
    info = query_gpu()
    assert info is not None
    assert not is_supported(info)
    try:
        require_supported_gpu()
    except GpuUnsupported:
        pass
    else:
        raise AssertionError("RTX 30 should be refused")
    assert main(["doctor"]) == 2
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4090,8.9,24576,20000")
    assert is_supported(query_gpu())  # type: ignore[arg-type]
    assert main(["doctor"]) == 0
    assert main(["doctor", "--mock"]) == 0


def test_plan_spills_and_keeps_moe_experts_on_cpu() -> None:
    tight = plan_server(
        weight_gb=19.8,
        budget_gb=20.0,
        total_gb=24.0,
        block_count=40,
        expert_count=0,
        desired_ctx=8192,
    )
    assert tight.spilled
    assert tight.context == 4096
    assert tight.cache_type == "q4_0"
    assert tight.n_gpu_layers < 999
    roomy = plan_server(
        weight_gb=8.0,
        budget_gb=20.0,
        total_gb=24.0,
        block_count=40,
        expert_count=8,
        desired_ctx=8192,
    )
    assert not roomy.spilled
    assert roomy.n_gpu_layers == 999
    assert roomy.cache_type == "q8_0"
    moe = plan_server(
        weight_gb=19.0,
        budget_gb=10.0,
        total_gb=24.0,
        block_count=32,
        expert_count=64,
        desired_ctx=8192,
    )
    assert moe.spilled
    assert moe.n_cpu_moe == 32
    assert moe.n_gpu_layers == 999
    assert moe.fit_target_mib == int(2 * 1024)


def test_thermal_waits_for_the_median_after_full_speed() -> None:
    clock = {"t": 0.0}
    guard = ThermalGuard(now=lambda: clock["t"])
    guard.update(GpuSample(HOT_C, 200.0, 0), now=10.0)
    assert not guard.should_pause(10.0)
    clock["t"] = FULL_SPEED_S
    guard.update(GpuSample(HOT_C, 200.0, 0), now=FULL_SPEED_S)
    assert guard.median_c() == HOT_C
    assert guard.should_pause(FULL_SPEED_S)
    missing = ThermalGuard(now=lambda: clock["t"])
    missing.t0 = clock["t"] - FULL_SPEED_S - 1
    missing.update(GpuSample(None, None, 0), now=clock["t"])
    assert not missing.should_pause(clock["t"])
