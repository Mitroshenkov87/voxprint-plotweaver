"""Choose context, layer offload, and KV cache type from the suite VRAM budget.

Weights that do not fit stay in system RAM (fewer GPU layers, or MoE experts via
--n-cpu-moe). On that spill the context and the batch are halved. The fit-target
passed to llama-server is the suite headroom, in MiB.
"""

from __future__ import annotations

from dataclasses import dataclass

from plotweaver.hardware import vram_headroom_gb


@dataclass(frozen=True)
class ServerPlan:
    n_gpu_layers: int
    context: int
    fit_target_mib: int
    n_cpu_moe: int
    cache_type: str
    batch: int
    ubatch: int
    spilled: bool


def plan_server(
    *,
    weight_gb: float,
    budget_gb: float,
    total_gb: float,
    block_count: int,
    expert_count: int,
    desired_ctx: int,
) -> ServerPlan:
    """One resident model. Never plan a footprint above the budget."""
    headroom_mib = max(1, int(vram_headroom_gb(total_gb) * 1024))
    reserve = min(1.5, max(0.4, budget_gb * 0.15))
    weight_budget = max(0.0, budget_gb - reserve)
    spill = weight_gb > weight_budget > 0 or (weight_gb > 0 and weight_budget <= 0)
    blocks = block_count if block_count > 0 else 64
    if expert_count > 0 and spill:
        n_gpu_layers = 999
        n_cpu_moe = blocks
    elif spill:
        fraction = 0.0 if weight_gb <= 0 else min(1.0, weight_budget / weight_gb)
        n_gpu_layers = max(1, int(blocks * fraction))
        n_cpu_moe = 0
    else:
        n_gpu_layers = 999
        n_cpu_moe = 0
    context = desired_ctx
    if spill:
        context = max(4096, desired_ctx // 2)
    cache = "q8_0" if not spill and (budget_gb - weight_gb) > 3 else "q4_0"
    batch = 256 if spill else 512
    ubatch = 128 if spill else 512
    return ServerPlan(
        n_gpu_layers=n_gpu_layers,
        context=context,
        fit_target_mib=headroom_mib,
        n_cpu_moe=n_cpu_moe,
        cache_type=cache,
        batch=batch,
        ubatch=ubatch,
        spilled=spill,
    )
