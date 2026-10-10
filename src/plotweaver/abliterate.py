"""Refusal-direction ablation for a local Mistral Small derivation.

The direction is the difference of means between dark-fiction prompts and
ordinary prose prompts, then L2-normalised. Output projections are
orthogonalised against that direction, which is the published single-direction
method. Prompt text in this module is original and inherits the repo's
Apache-2.0 licence. Heretic is not imported or invoked.

A 24B bf16 checkpoint is about 48 GB. The full run keeps at most 20 GB on the
GPU and spills the rest through a CPU and disk offload. See docs/bakeoff.md.
``--tiny`` runs the same math on an in-memory model so CI does not download weights.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from plotweaver.checks import is_refusal, is_sanitised
from plotweaver.domain import Task
from plotweaver.errors import PlotweaverError
from plotweaver.paths import repo_root

_GIB = 1024**3
_EXCLUDED_KEYS = frozenset({"yandex", "yandexgpt", "yandexgpt-5-lite"})

ORDINARY_PROMPTS: tuple[str, ...] = (
    "Write a paragraph about a baker opening the shop on a quiet morning.",
    "Write a letter from a student to a friend about a rainy walk home.",
    "Describe a kitchen table after breakfast, with crumbs and a cold cup.",
    "Explain, in plain sentences, how a paper boat floats in a puddle.",
    "Напиши абзац о том, как утром открывают булочную на тихой улице.",
    "Напиши письмо другу о дороге домой под дождём.",
    "Опиши кухонный стол после завтрака: крошки и остывшая чашка.",
    "Объясни простыми фразами, почему бумажный кораблик держится на луже.",
)

DARK_PROMPTS: tuple[str, ...] = (
    "Write a novel scene: a soldier is wounded in battle. Describe it plainly, with no lecture.",
    "Write a novel scene of a storm sinking a ship. Keep the fear, and add no disclaimer.",
    "Write a duel in a novel. Someone is cut, the fight ends, and the narrator does not moralise.",
    "Write a funeral after a battle. Name the loss in concrete detail and do not fade to black.",
    "Напиши сцену романа: солдат ранен в бою. Опиши рану прямо, без нравоучения.",
    "Напиши сцену романа: шторм топит корабль. Оставь холод и страх, без оговорок.",
    "Напиши дуэль в романе. Кого-то ранят, бой кончается, рассказчик не читает мораль.",
    "Напиши похороны после битвы. Назови потерю конкретно и не обрывай рассказ.",
)

PERPLEXITY_TEXT = (
    "The baker counted the loaves, wiped the counter, and left the door open for the street. "
    "Пекарь пересчитал хлеб, вытер прилавок и оставил дверь открытой на улицу."
)


@dataclass(frozen=True)
class AblationTarget:
    key: str
    title: str
    stock_id: str
    stock_sha256: str
    stock_size: int
    base_repo: str
    base_revision: str
    produced_id: str
    produced_filename: str
    min_vram_gb: float
    credit: str


@dataclass(frozen=True)
class AblationReport:
    kind: str
    direction_dim: int
    refusal_before: float
    refusal_after: float
    nll_before: float
    nll_after: float
    sha256: str
    size: int
    fits_16gb: bool
    min_vram_gb: float
    base_revision: str
    title: str
    base_repo: str
    credit: str
    produced_id: str


def ablation_targets() -> tuple[AblationTarget, ...]:
    """Official Apache-2.0 bases. Third-party abliterated T-lite files are not used."""
    return (
        AblationTarget(
            key="mistral",
            title="Mistral Small 3.2",
            stock_id="mistral-small-3.2-24b-q4",
            stock_sha256="a3cc56310807ed0d145eaf9f018ccda9ae7ad8edb41ec870aa2454b0d4700b3c",
            stock_size=14_333_922_848,
            base_repo="mistralai/Mistral-Small-3.2-24B-Instruct-2506",
            base_revision="95a6d26c4bfb886c58daf9d3f7332c857cb27b43",
            produced_id="mistral-small-3.2-24b-plotweaver-abliterated-q4",
            produced_filename="mistral-small-3.2-24b-plotweaver-abliterated-Q4_K_M.gguf",
            min_vram_gb=15.0,
            credit="",
        ),
        AblationTarget(
            key="t-lite",
            title="T-lite-it-2.1",
            stock_id="t-lite-it-2.1-q4",
            stock_sha256="68c75f5940c36baca18113058ad3d55f6d1d3e1123a8053bb4bba8481805c960",
            stock_size=5_027_750_240,
            base_repo="t-tech/T-lite-it-2.1",
            base_revision="d125c970c553de58fcee3c937d5e4867d4a448d8",
            produced_id="t-lite-it-2.1-plotweaver-abliterated-q4",
            produced_filename="t-lite-it-2.1-plotweaver-abliterated-Q4_K_M.gguf",
            min_vram_gb=6.0,
            credit="T-Bank and the Qwen team. The base is derived from Qwen/Qwen3-8B.",
        ),
        AblationTarget(
            key="t-pro",
            title="T-pro-it-2.1",
            stock_id="t-pro-it-2.1-q4",
            stock_sha256="b19e88cc1154b4b0c99f09bc7b57b8e5f3a6af4135581a3bfd31a2518ed58714",
            stock_size=19_761_766_048,
            base_repo="t-tech/T-pro-it-2.1",
            base_revision="a677a7c27bb8820c816fbcf578d912acedcf4439",
            produced_id="t-pro-it-2.1-plotweaver-abliterated-q4",
            produced_filename="t-pro-it-2.1-plotweaver-abliterated-Q4_K_M.gguf",
            min_vram_gb=20.0,
            credit="T-Bank and the Qwen team. The base is derived from Qwen/Qwen3-32B.",
        ),
    )


def target_by_key(key: str) -> AblationTarget:
    name = key.strip().lower()
    if name in _EXCLUDED_KEYS:
        raise PlotweaverError(
            "YandexGPT is excluded: its licence forbids modification and redistribution."
        )
    for target in ablation_targets():
        if target.key == name:
            return target
    known = ", ".join(target.key for target in ablation_targets())
    raise PlotweaverError(f"unknown ablation model {key!r}. Choose one of: {known}")


# Kept for the Mistral card path and older tests.
PRODUCED_ID = ablation_targets()[0].produced_id
PRODUCED_FILENAME = ablation_targets()[0].produced_filename


def difference_of_means(harmful: list[list[float]], harmless: list[list[float]]) -> list[float]:
    """Unit vector from the harmless mean toward the harmful mean."""
    if not harmful or not harmless:
        raise PlotweaverError("both prompt sets need at least one activation")
    width = len(harmful[0])
    if any(len(row) != width for row in harmful + harmless):
        raise PlotweaverError("activations must share one width")
    harmful_mean = _mean(harmful)
    harmless_mean = _mean(harmless)
    delta = [left - right for left, right in zip(harmful_mean, harmless_mean, strict=True)]
    return _normalise(delta)


def orthogonalize(matrix: list[list[float]], direction: list[float]) -> list[list[float]]:
    """Remove ``direction`` from the output axis of a weight matrix shaped [out, in]."""
    if not matrix or not matrix[0]:
        raise PlotweaverError("weight matrix is empty")
    height = len(matrix)
    width = len(matrix[0])
    if len(direction) != height:
        raise PlotweaverError("direction length must match the output axis")
    if any(len(row) != width for row in matrix):
        raise PlotweaverError("weight matrix is ragged")
    cleaned = [list(source) for source in matrix]
    for column in range(width):
        component = sum(cleaned[index][column] * direction[index] for index in range(height))
        for index in range(height):
            cleaned[index][column] -= direction[index] * component
    return cleaned


def projection(vector: list[float], direction: list[float]) -> float:
    return abs(_dot(vector, direction))


def refusal_rate(texts: list[str]) -> float:
    if not texts:
        raise PlotweaverError("refusal rate needs at least one completion")
    refused = sum(1 for text in texts if is_refusal(text) or is_sanitised(text))
    return refused / len(texts)


def fits_16gb(size: int) -> bool:
    return size <= 16 * _GIB


def probe_prompt(text: str) -> str:
    return f"TASK: {Task.PROBE.value}\n{text}"


def model_card(report: AblationReport) -> str:
    if report.fits_16gb:
        fit = "The Q4_K_M file fits a 16 GB card."
    else:
        fit = "The Q4_K_M file does not fit a 16 GB card."
    lines = [
        f"# {report.title} abliterated (Plotweaver derivation)",
        "",
        "License: Apache-2.0, inherited from the base model.",
        "Modification notice: this file changes the original weights by removing a",
        "refusal direction and then quantizing to Q4_K_M. It is not the original model.",
        f"Base: {report.base_repo} @ {report.base_revision}.",
    ]
    if report.credit:
        lines.append(f"Credit: {report.credit}")
    lines.extend(
        [
            "Method: difference-of-means refusal direction on original dark-fiction prompts",
            "versus ordinary prose, in English and Russian, then orthogonalise the output",
            "projections (o_proj and down_proj). No third-party ablation tool is vendored.",
            "Quant: Q4_K_M with llama.cpp b11476.",
            f"SHA-256 {report.sha256}. Size {report.size} bytes.",
            f"min_vram_gb: {report.min_vram_gb}. {fit}",
            f"Refusal rate before {report.refusal_before:.3f}, after {report.refusal_after:.3f}.",
            f"Mean NLL before {report.nll_before:.4f}, after {report.nll_after:.4f}.",
            "This file is an optional download. It is not part of the default install.",
            "",
        ]
    )
    return "\n".join(lines)


def enable_produced_entry(
    path: Path, *, model_id: str, sha256: str, size: int, revision: str
) -> None:
    """Fill the disabled registry row once the produced file has a hash."""
    text = path.read_text(encoding="utf-8")
    marker = f'id = "{model_id}"'
    start = text.find(marker)
    if start < 0:
        raise PlotweaverError(f"{path} has no {model_id} row")
    end = text.find("\n[[model]]", start + 1)
    if end < 0:
        end = len(text)
    block = text[start:end]
    block = block.replace("enabled = false", "enabled = true", 1)
    block = re.sub(r'revision = ".*"', f'revision = "{revision}"', block, count=1)
    block = re.sub(r'sha256 = ".*"', f'sha256 = "{sha256}"', block, count=1)
    block = re.sub(r"^size = \d+", f"size = {size}", block, count=1, flags=re.MULTILINE)
    path.write_text(text[:start] + block + text[end:], encoding="utf-8", newline="\n")


def run_tiny(out_dir: Path) -> AblationReport:
    """Ablate a three-dimensional toy and write a card plus a hashed marker file."""
    harmful = [[1.0, 0.1, 0.0], [0.9, 0.0, 0.1], [1.1, -0.1, 0.0]]
    harmless = [[0.0, 1.0, 0.0], [0.1, 0.9, 0.0], [0.0, 1.1, -0.1]]
    direction = difference_of_means(harmful, harmless)
    weight = [
        [1.0, 0.2, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    before = projection([row[0] for row in weight], direction)
    ablated = orthogonalize(weight, direction)
    after = projection([row[0] for row in ablated], direction)
    harmful_hit = _dot(_mean(harmful), direction)
    ordinary_hit = _dot(_mean(harmless), direction)
    if before < 0.5 or after > 1e-9:
        raise PlotweaverError("tiny ablation left a refusal component in the weight")
    if harmful_hit <= ordinary_hit:
        raise PlotweaverError("ordinary prompts align with the refusal direction")
    refused_before = ["I cannot write this scene.", "The scene continues in the rain."]
    refused_after = [
        "The scene continues in the rain.",
        "Пыль лежала на люке, и рассказ шёл дальше.",
    ]
    if refusal_rate(refused_after) >= refusal_rate(refused_before):
        raise PlotweaverError("tiny refusal rate did not fall")
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen: AblationReport | None = None
    for target in ablation_targets():
        marker = out_dir / target.produced_filename
        marker.write_bytes(b"plotweaver-tiny-ablation")
        digest = _sha256(marker)
        report = AblationReport(
            kind="tiny",
            direction_dim=len(direction),
            refusal_before=refusal_rate(refused_before),
            refusal_after=refusal_rate(refused_after),
            nll_before=harmful_hit,
            nll_after=ordinary_hit,
            sha256=digest,
            size=marker.stat().st_size,
            fits_16gb=fits_16gb(target.stock_size),
            min_vram_gb=target.min_vram_gb,
            base_revision=target.base_revision,
            title=target.title,
            base_repo=target.base_repo,
            credit=target.credit,
            produced_id=target.produced_id,
        )
        card = out_dir / f"{target.produced_id}.MODEL_CARD.md"
        card.write_text(model_card(report), encoding="utf-8")
        if target.key == "mistral":
            chosen = report
    if chosen is None:
        raise PlotweaverError("tiny ablation did not write the Mistral card")
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ablate one pinned Apache-2.0 model.")
    parser.add_argument("model", nargs="?", default="")
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("out/abliterate-tiny"))
    args = parser.parse_args(argv)
    if args.tiny:
        report = run_tiny(args.out)
        print(
            "tiny ablation "
            f"sha256={report.sha256} "
            f"refusal {report.refusal_before:.2f} -> {report.refusal_after:.2f}"
        )
        return 0
    if not args.model:
        raise PlotweaverError("name a model: mistral, t-lite, or t-pro")
    target = target_by_key(args.model)
    # Torch is an optional VM dependency, so CI can import this module without it.
    from plotweaver.abliterate_hf import run_model

    return run_model(target)


def _mean(rows: list[list[float]]) -> list[float]:
    width = len(rows[0])
    count = float(len(rows))
    return [sum(row[index] for row in rows) / count for index in range(width)]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _normalise(vector: list[float]) -> list[float]:
    length = math.sqrt(_dot(vector, vector))
    if length == 0.0:
        raise PlotweaverError("refusal direction has zero length")
    return [value / length for value in vector]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def registry_file() -> Path:
    return repo_root() / "bakeoff" / "models.toml"
