"""Full Mistral Small ablation on a 24 GB GPU with CPU and disk offload.

PyTorch and Transformers are Apache-2.0. llama.cpp b11476 is MIT. This module
does not vendor, import, or invoke Heretic.

Disk and memory for the 24B bf16 base (about 48 GB of weights):

- GPU: cap the device map at 20 GB so a 24 GB RTX 4090 keeps headroom.
- CPU RAM: 64 GB recommended. Layers that do not fit are written to ``offload/``.
- Disk: about 120 GB free. That covers the Hugging Face cache (~48 GB), the
  offload scratch, an F16 GGUF (~48 GB), and the Q4_K_M file (~14 GB).

The stock Q4_K_M is 14,333,922,848 bytes and fits a 16 GB card. The ablated
quant uses the same architecture and the same Q4_K_M target, so it fits the same way.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from plotweaver.abliterate import (
    DARK_PROMPTS,
    ORDINARY_PROMPTS,
    PERPLEXITY_TEXT,
    AblationReport,
    AblationTarget,
    enable_produced_entry,
    fits_16gb,
    model_card,
    probe_prompt,
    refusal_rate,
    registry_file,
)
from plotweaver.errors import PlotweaverError
from plotweaver.llama_release import LLAMA_BUILD
from plotweaver.paths import gguf_dir, llama_runtime_dir
from plotweaver.registry import download_model, load_registry, registry_path


def run_model(target: AblationTarget) -> int:
    stock = _stock_entry(target.stock_id)
    if stock.sha256 != target.stock_sha256 or stock.base_revision != target.base_revision:
        raise PlotweaverError(f"stock pin for {target.key} does not match the ablation constants")
    print(f"Checking the pinned stock GGUF for {target.key}.")
    download_model(stock)
    work = gguf_dir() / "abliterate-work" / target.key
    work.mkdir(parents=True, exist_ok=True)
    print("Loading the base in chunks (20 GB GPU cap, CPU and disk offload).")
    tokenizer, model = _load_chunked(target, work / "offload")
    before_refusal, before_nll = _measure(tokenizer, model)
    direction = _direction(tokenizer, model)
    _ablate(model, direction)
    after_refusal, after_nll = _measure(tokenizer, model)
    if after_refusal >= before_refusal:
        raise PlotweaverError("ablation did not lower the refusal rate")
    if after_nll > before_nll * 1.5:
        raise PlotweaverError("ablation raised the mean NLL by more than half")
    exported = work / "hf-ablated"
    model.save_pretrained(exported)
    tokenizer.save_pretrained(exported)
    quant = _convert_and_quantize(exported, work, target.produced_filename)
    digest = _hash_file(quant)
    produced = gguf_dir() / target.produced_filename
    if quant.resolve() != produced.resolve():
        produced.write_bytes(quant.read_bytes())
    report = AblationReport(
        kind=target.key,
        direction_dim=int(direction.shape[0]),
        refusal_before=before_refusal,
        refusal_after=after_refusal,
        nll_before=before_nll,
        nll_after=after_nll,
        sha256=digest,
        size=produced.stat().st_size,
        fits_16gb=fits_16gb(produced.stat().st_size),
        min_vram_gb=target.min_vram_gb,
        base_revision=target.base_revision,
        title=target.title,
        base_repo=target.base_repo,
        credit=target.credit,
        produced_id=target.produced_id,
    )
    card = gguf_dir() / f"{target.produced_id}.MODEL_CARD.md"
    card.write_text(model_card(report), encoding="utf-8")
    enable_produced_entry(
        registry_file(),
        model_id=target.produced_id,
        sha256=digest,
        size=report.size,
        revision=target.base_revision,
    )
    print(f"wrote {produced} sha256={digest} fits_16gb={report.fits_16gb}")
    return 0


def _stock_entry(stock_id: str):
    for entry in load_registry(registry_path()):
        if entry.id == stock_id:
            return entry
    raise PlotweaverError(f"{stock_id} is not in the registry")


def _load_chunked(target: AblationTarget, offload: Path) -> tuple[Any, Any]:
    offload.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(target.base_repo, revision=target.base_revision)
    model = AutoModelForCausalLM.from_pretrained(
        target.base_repo,
        revision=target.base_revision,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        max_memory={0: "20GiB", "cpu": "64GiB"},
        offload_folder=str(offload),
        low_cpu_mem_usage=True,
    )
    model.eval()
    return tokenizer, model


def _direction(tokenizer: Any, model: Any) -> torch.Tensor:
    harmful = _hidden_mean(tokenizer, model, DARK_PROMPTS)
    harmless = _hidden_mean(tokenizer, model, ORDINARY_PROMPTS)
    direction = harmful - harmless
    return direction / direction.norm()


def _hidden_mean(tokenizer: Any, model: Any, texts: tuple[str, ...]) -> torch.Tensor:
    rows: list[torch.Tensor] = []
    layer = _middle_layer(model)
    for text in texts:
        encoded = tokenizer(text, return_tensors="pt")
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        with torch.no_grad():
            output = model(**encoded, output_hidden_states=True)
        hidden = output.hidden_states[layer][0, -1].float().cpu()
        rows.append(hidden)
    return torch.stack(rows).mean(dim=0)


def _middle_layer(model: Any) -> int:
    layers = model.model.layers
    return max(1, len(layers) // 2)


def _ablate(model: Any, direction: torch.Tensor) -> None:
    with torch.no_grad():
        for name, param in model.named_parameters():
            if not name.endswith(("o_proj.weight", "down_proj.weight")):
                continue
            vector = direction.to(device=param.device, dtype=torch.float32)
            if param.shape[0] != vector.shape[0]:
                continue
            weight = param.data.float()
            component = vector @ weight
            param.data.copy_((weight - vector[:, None] * component).to(param.dtype))


def _measure(tokenizer: Any, model: Any) -> tuple[float, float]:
    texts: list[str] = []
    for prompt in DARK_PROMPTS:
        encoded = tokenizer(probe_prompt(prompt), return_tensors="pt")
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        with torch.no_grad():
            generated = model.generate(**encoded, max_new_tokens=64, do_sample=False)
        new_tokens = generated[0, encoded["input_ids"].shape[1] :]
        texts.append(tokenizer.decode(new_tokens, skip_special_tokens=True))
    nll = _nll(tokenizer, model, PERPLEXITY_TEXT)
    return refusal_rate(texts), nll


def _nll(tokenizer: Any, model: Any, text: str) -> float:
    encoded = tokenizer(text, return_tensors="pt")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    labels = encoded["input_ids"]
    with torch.no_grad():
        loss = model(**encoded, labels=labels).loss
    return float(loss.float().cpu())


def _convert_and_quantize(exported: Path, work: Path, filename: str) -> Path:
    convert = _convert_script()
    quantize = _quantize_bin()
    f16 = work / "ablated-f16.gguf"
    q4 = gguf_dir() / filename
    subprocess.run(
        ["python", str(convert), str(exported), "--outfile", str(f16), "--outtype", "f16"],
        check=True,
    )
    subprocess.run([str(quantize), str(f16), str(q4), "Q4_K_M"], check=True)
    return q4


def _convert_script() -> Path:
    src = Path(f"llama.cpp-{LLAMA_BUILD}")
    candidates = [
        llama_runtime_dir() / "convert_hf_to_gguf.py",
        Path.home() / src / "convert_hf_to_gguf.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise PlotweaverError(
        "convert_hf_to_gguf.py from llama.cpp "
        f"{LLAMA_BUILD} was not found. Clone that tag next to the runtime "
        "(the Vulkan archive has llama-quantize, not the Python converter)."
    )


def _quantize_bin() -> Path:
    folder = llama_runtime_dir()
    for name in ("llama-quantize", "llama-quantize.exe"):
        path = folder / name
        if path.is_file():
            return path
    raise PlotweaverError(
        f"llama-quantize from llama.cpp {LLAMA_BUILD} is not in {folder}. "
        "scripts/bakeoff.sh downloads that runtime on a real bake-off."
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
