"""16 GB fit experiment: smaller quants, KV cache, and a hard 13 GiB budget.

Weights plus KV cache must stay at or under 13 GiB so a 16 GB card keeps
2-3 GB free. On a 24 GB machine the probe passes ``--fit-target`` of that
budget and records a failure when the load spills to CPU or the sum exceeds it.
``--tiny`` checks the same table, resume rule, and recommendation without weights.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from plotweaver.atomic import read_json, write_json, write_text
from plotweaver.errors import PlotweaverError

BUDGET_BYTES = 13 * 1024**3
FIT_TARGET_MIB = 13 * 1024
CONTEXTS = (8192, 16384)
KV_TYPES = ("q8_0", "q4_0")
_DONE = frozenset({"completed", "over-budget"})
_MIB = 1024**2

_DEVICE_BUFFER = re.compile(
    r"(?P<device>CPU|Vulkan\d+|CUDA\d+)\s+(?P<kind>model|KV) buffer size"
    r"\s*=\s*(?P<mib>[0-9.]+)\s+MiB",
    re.IGNORECASE,
)
_KV_PLAIN = re.compile(
    r"KV cache(?:_unified)?:?\s+size\s*=\s*([0-9.]+)\s+MiB",
    re.IGNORECASE,
)
_PROMPT_TPS = re.compile(r"prompt eval time = .*?([0-9.]+) tokens per second")
_GEN_TPS = re.compile(r"(?<!prompt )eval time = .*?([0-9.]+) tokens per second")
_BENCH_PP = re.compile(r"\|\s*pp\d+\s*\|\s*([0-9.]+)")
_BENCH_TG = re.compile(r"\|\s*tg\d+\s*\|\s*([0-9.]+)")
_PPL = re.compile(r"Final estimate:\s*PPL\s*=\s*([0-9.]+)")


@dataclass(frozen=True)
class Family:
    id: str
    repo: str
    revision: str
    baseline_id: str
    source_filename: str
    source_sha256: str
    source_size: int
    quants: tuple[str, ...]
    imatrix: bool
    registry_quants: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LoadReport:
    weight_bytes: int
    kv_bytes: int
    spilled: bool


def families() -> tuple[Family, ...]:
    """Candidates. Baselines are the registry Q4_K_M files. New quants are built on the VM."""
    return (
        Family(
            id="qwen3.6-27b-abliterated",
            repo="mradermacher/Huihui-Qwen3.6-27B-abliterated-GGUF",
            revision="530e4cbae44f7a27396a8705f9fe802764ba6103",
            baseline_id="qwen3.6-27b-abliterated-q4",
            source_filename="Huihui-Qwen3.6-27B-abliterated.Q8_0.gguf",
            source_sha256="",
            source_size=0,
            quants=("IQ4_XS", "IQ3_M", "Q3_K_M"),
            imatrix=True,
            registry_quants=(),
        ),
        Family(
            id="gemma-4-31b-abliterated",
            repo="paperscarecrow/Gemma-4-31B-it-abliterated",
            revision="2491ee58472b82a2372d288f982943b9d5e6a82c",
            baseline_id="gemma-4-31b-abliterated-q4",
            source_filename="gemma-4-31b-abliterated-Q8_0.gguf",
            source_sha256="",
            source_size=0,
            quants=("IQ4_XS", "IQ3_M", "Q3_K_M"),
            imatrix=True,
            registry_quants=(),
        ),
        Family(
            id="mistral-small-3.2-24b-abliterated",
            repo="mradermacher/Huihui-Mistral-Small-3.2-24B-Instruct-2506-abliterated-llamacppfixed-GGUF",
            revision="4737318711c389a453d274fea0ee9b2bd009b573",
            baseline_id="mistral-small-3.2-24b-abliterated-q4",
            source_filename=(
                "Huihui-Mistral-Small-3.2-24B-Instruct-2506-abliterated-llamacppfixed.Q8_0.gguf"
            ),
            source_sha256="",
            source_size=0,
            quants=("Q4_K_M", "Q5_K_M"),
            imatrix=True,
            registry_quants=(),
        ),
        Family(
            id="t-lite-it-2.1",
            repo="t-tech/T-lite-it-2.1-GGUF",
            revision="fc10186e59064c2e74f59c3d5dbce233931b3b81",
            baseline_id="t-lite-it-2.1-q4",
            source_filename="",
            source_sha256="",
            source_size=0,
            quants=("Q5_K_M",),
            imatrix=False,
            registry_quants=(("Q5_K_M", "t-lite-it-2.1-q5"),),
        ),
        Family(
            id="t-pro-it-2.1",
            repo="t-tech/T-pro-it-2.1-GGUF",
            revision="cf18787d8901c26ca9334812e7ff8070f2ddab4a",
            baseline_id="t-pro-it-2.1-q4",
            source_filename="T-pro-it-2.1-Q8_0.gguf",
            source_sha256="af2b3a761473a95ca31ab9b8647b9dc4288604a4a71f795ffd9402d2938c7621",
            source_size=34_816_397_344,
            quants=("IQ4_XS", "IQ3_M"),
            imatrix=True,
            registry_quants=(),
        ),
    )


def within_budget(weight_bytes: int, kv_bytes: int, spilled: bool) -> bool:
    """True when the full model stayed on GPU and weights + KV are inside 13 GiB."""
    return not spilled and weight_bytes + kv_bytes <= BUDGET_BYTES


def parse_load_log(text: str) -> LoadReport:
    """Read llama.cpp load lines. A CPU model buffer means the fit cap spilled."""
    weight = 0
    kv = 0
    spilled = False
    tagged = False
    for match in _DEVICE_BUFFER.finditer(text):
        tagged = True
        amount = int(float(match.group("mib")) * _MIB)
        device = match.group("device").upper()
        kind = match.group("kind").lower()
        if device == "CPU" and kind == "model" and amount > _MIB:
            spilled = True
            continue
        if device == "CPU":
            continue
        if kind == "model":
            weight += amount
        else:
            kv += amount
    if kv == 0:
        plain = _KV_PLAIN.search(text)
        if plain is not None:
            kv = int(float(plain.group(1)) * _MIB)
            tagged = True
    if not tagged or weight <= 0:
        raise PlotweaverError("llama.cpp log has no model buffer size")
    return LoadReport(weight, kv, spilled)


def parse_tokens_per_second(text: str) -> tuple[float, float]:
    prompt = _BENCH_PP.search(text)
    gen = _BENCH_TG.search(text)
    if prompt and gen:
        return float(prompt.group(1)), float(gen.group(1))
    prompt_line = _PROMPT_TPS.search(text)
    gen_line = _GEN_TPS.search(text)
    if prompt_line and gen_line:
        return float(prompt_line.group(1)), float(gen_line.group(1))
    raise PlotweaverError("llama.cpp log has no prompt and generation tokens/s")


def parse_perplexity(text: str) -> float:
    match = _PPL.search(text)
    if match is None:
        raise PlotweaverError("llama-perplexity log has no final PPL")
    return float(match.group(1))


def quality_loss(
    *,
    perplexity: float,
    baseline_perplexity: float,
    synopsis_score: float,
    baseline_synopsis_score: float,
) -> float:
    """Perplexity increase plus the drop in the short synopsis score. Lower is better."""
    if baseline_perplexity <= 0:
        raise PlotweaverError("baseline perplexity must be positive")
    ppl_delta = (perplexity - baseline_perplexity) / baseline_perplexity
    return (baseline_synopsis_score - synopsis_score) + ppl_delta


def probe_command(binary: Path, model: Path, *, context: int, kv: str, prompt: str) -> list[str]:
    """One llama-cli launch. The fit target is the 13 GiB budget, not the 24 GB card."""
    if kv not in KV_TYPES:
        raise PlotweaverError(f"unsupported KV cache type: {kv}")
    if context not in CONTEXTS:
        raise PlotweaverError(f"unsupported context: {context}")
    return [
        str(binary),
        "-m",
        str(model),
        "-p",
        prompt,
        "-n",
        "64",
        "-c",
        str(context),
        "-ngl",
        "999",
        "--fit",
        "on",
        "--fit-target",
        str(FIT_TARGET_MIB),
        "-fa",
        "on",
        "-ctk",
        kv,
        "-ctv",
        kv,
        "--temp",
        "0",
        "-no-cnv",
    ]


def row_key(row: dict[str, object]) -> str:
    return f"{row['model']}|{row['quant']}|{row['kv']}|{row['context']}"


def recommend(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Best row that fits. Prefer 16k context, then lower quality loss, then speed."""
    eligible = [
        row for row in rows if row.get("within_budget") is True and row.get("status") != "error"
    ]
    if not eligible:
        return None
    longest = max(_whole(row["context"]) for row in eligible)
    pool = [row for row in eligible if _whole(row["context"]) == longest]
    pool.sort(
        key=lambda row: (
            _num(row["quality_loss"]),
            -_num(row["gen_tps"]),
            _whole(row["weight_bytes"]) + _whole(row["kv_bytes"]),
        )
    )
    return pool[0]


def render_csv(rows: list[dict[str, object]]) -> str:
    fields = [
        "model",
        "quant",
        "kv",
        "context",
        "flash_attn",
        "weight_bytes",
        "kv_bytes",
        "within_budget",
        "spilled",
        "perplexity",
        "baseline_perplexity",
        "quality_loss",
        "refusal_rate",
        "baseline_refusal",
        "synopsis_score",
        "prompt_tps",
        "gen_tps",
        "status",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def render_markdown(rows: list[dict[str, object]]) -> str:
    choice = recommend(rows)
    lines = [
        "# 16 GB fit",
        "",
        "Budget is weights + KV cache <= 13 GiB, with flash attention on.",
        "A row fails when llama.cpp spills the model to CPU or the sum exceeds 13 GiB.",
        "",
        "| Model | Quant | KV | Context | GiB | Budget | Loss | Refusal | Prompt t/s | Gen t/s |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        total = (_whole(row["weight_bytes"]) + _whole(row["kv_bytes"])) / (1024**3)
        budget = "fit" if row["within_budget"] else "FAIL"
        cells = [
            str(row["model"]),
            str(row["quant"]),
            str(row["kv"]),
            str(row["context"]),
            f"{total:.2f}",
            budget,
            f"{_num(row['quality_loss']):.3f}",
            f"{_num(row['refusal_rate']):.2f}",
            f"{_num(row['prompt_tps']):.1f}",
            f"{_num(row['gen_tps']):.1f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "## Recommendation", ""])
    if choice is None:
        lines.append("No variant kept weights and KV cache inside 13 GiB.")
    else:
        lines.append(
            "Best 16 GB option: {model} {quant}, KV {kv}, context {context}. "
            "Quality loss against that model's Q4_K_M is {loss:.3f}. "
            "Prompt {prompt:.1f} t/s, generation {gen:.1f} t/s.".format(
                model=choice["model"],
                quant=choice["quant"],
                kv=choice["kv"],
                context=choice["context"],
                loss=_num(choice["quality_loss"]),
                prompt=_num(choice["prompt_tps"]),
                gen=_num(choice["gen_tps"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def store_rows(out: Path, rows: list[dict[str, object]]) -> None:
    ordered = sorted(rows, key=row_key)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "results.json", {"budget_bytes": BUDGET_BYTES, "rows": ordered})
    write_text(out / "summary.csv", render_csv(ordered))
    write_text(out / "summary.md", render_markdown(ordered))


def merge_rows(
    existing: list[dict[str, object]], incoming: list[dict[str, object]]
) -> list[dict[str, object]]:
    by_key = {row_key(row): row for row in existing}
    for row in incoming:
        key = row_key(row)
        previous = by_key.get(key)
        if previous is not None and str(previous.get("status")) in _DONE:
            continue
        by_key[key] = row
    return sorted(by_key.values(), key=row_key)


def load_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    payload = read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise PlotweaverError(f"{path} has no rows list")
    return [row for row in rows if isinstance(row, dict)]


def tiny_rows() -> list[dict[str, object]]:
    """Fixed measurements. One 16k row fits; a heavier quant is over the 13 GiB budget."""
    fit_weight = 11 * 1024**3
    fit_kv_8k = 400 * _MIB
    fit_kv_16k = 800 * _MIB
    over_weight = 14 * 1024**3
    return [
        _tiny_row(
            "qwen3.6-27b-abliterated",
            "IQ3_M",
            "q4_0",
            8192,
            fit_weight,
            fit_kv_8k,
            0.04,
            30.0,
        ),
        _tiny_row(
            "qwen3.6-27b-abliterated",
            "IQ3_M",
            "q4_0",
            16384,
            fit_weight,
            fit_kv_16k,
            0.04,
            28.0,
        ),
        _tiny_row(
            "qwen3.6-27b-abliterated",
            "IQ4_XS",
            "q8_0",
            8192,
            over_weight,
            fit_kv_8k,
            0.01,
            40.0,
        ),
        _tiny_row(
            "gemma-4-31b-abliterated",
            "Q3_K_M",
            "q4_0",
            16384,
            fit_weight,
            fit_kv_16k,
            0.22,
            18.0,
        ),
        _tiny_row(
            "mistral-small-3.2-24b-abliterated",
            "Q5_K_M",
            "q8_0",
            8192,
            over_weight,
            fit_kv_8k,
            0.02,
            35.0,
        ),
    ]


def run_tiny(out: Path) -> dict[str, object] | None:
    existing = load_rows(out / "results.json")
    merged = merge_rows(existing, tiny_rows())
    store_rows(out, merged)
    return recommend(merged)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit abliterated models into a 16 GB budget.")
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("out/fit16"))
    args = parser.parse_args(argv)
    if args.tiny:
        choice = run_tiny(args.out)
        if choice is None:
            print("tiny fit: no row inside the budget")
            return 2
        print(
            "tiny fit: "
            f"{choice['model']} {choice['quant']} ctx {choice['context']} kv {choice['kv']}"
        )
        return 0
    # The live runner downloads Q8 sources and starts llama.cpp. CI stops at --tiny.
    from plotweaver.fit16_live import run_live

    return run_live(args.out)


def _num(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise PlotweaverError("fit row field is not a number")


def _whole(value: object) -> int:
    if isinstance(value, int):
        return value
    raise PlotweaverError("fit row field is not an integer")


def _tiny_row(
    model: str,
    quant: str,
    kv: str,
    context: int,
    weight: int,
    kv_bytes: int,
    loss: float,
    gen_tps: float,
) -> dict[str, object]:
    spilled = False
    fits = within_budget(weight, kv_bytes, spilled)
    return {
        "model": model,
        "quant": quant,
        "kv": kv,
        "context": context,
        "flash_attn": True,
        "weight_bytes": weight,
        "kv_bytes": kv_bytes,
        "within_budget": fits,
        "spilled": spilled,
        "perplexity": 8.0 + loss,
        "baseline_perplexity": 8.0,
        "quality_loss": loss,
        "refusal_rate": 0.1,
        "baseline_refusal": 0.2,
        "synopsis_score": 0.9,
        "prompt_tps": gen_tps + 20.0,
        "gen_tps": gen_tps,
        "status": "completed" if fits else "over-budget",
    }
