"""VM half of the 16 GB fit: build imatrix quants, then measure each cell.

llama.cpp b11476 supplies llama-imatrix, llama-quantize, llama-perplexity, and
llama-cli. The calibration file is original Russian fiction under Apache-2.0.
A finished row is skipped, so the command can be run again after a crash.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import httpx

from plotweaver.abliterate import DARK_PROMPTS, refusal_rate
from plotweaver.atomic import read_json, write_json
from plotweaver.bakeoff import load_synopses
from plotweaver.errors import PlotweaverError
from plotweaver.fit16 import (
    CONTEXTS,
    FIT_TARGET_MIB,
    KV_TYPES,
    Family,
    families,
    load_rows,
    parse_load_log,
    parse_perplexity,
    parse_tokens_per_second,
    probe_command,
    quality_loss,
    recommend,
    store_rows,
    within_budget,
)
from plotweaver.llama_release import ensure_llama_server
from plotweaver.paths import gguf_dir, repo_root
from plotweaver.registry import download_model, load_registry, registry_path, verify_file

_USER_AGENT = "plotweaver"


def run_live(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    server = ensure_llama_server()
    cli = _sibling(server, "llama-cli")
    perplexity = _sibling(server, "llama-perplexity")
    imatrix_bin = _sibling(server, "llama-imatrix")
    quantize_bin = _sibling(server, "llama-quantize")
    calibration = repo_root() / "bakeoff" / "calibration" / "ru-fiction.txt"
    if not calibration.is_file():
        raise PlotweaverError(f"missing calibration text: {calibration}")
    rows = load_rows(out / "results.json")
    for family in families():
        rows = _family(
            family,
            out=out,
            rows=rows,
            cli=cli,
            perplexity=perplexity,
            imatrix_bin=imatrix_bin,
            quantize_bin=quantize_bin,
            calibration=calibration,
        )
    store_rows(out, rows)
    return 0 if recommend(rows) is not None else 2


def _family(
    family: Family,
    *,
    out: Path,
    rows: list[dict[str, object]],
    cli: Path,
    perplexity: Path,
    imatrix_bin: Path,
    quantize_bin: Path,
    calibration: Path,
) -> list[dict[str, object]]:
    baseline = _registry_file(family.baseline_id)
    pinned = dict(family.registry_quants)
    needs_build = any(quant not in pinned and quant != "Q4_K_M" for quant in family.quants)
    source = baseline
    imatrix = out / f"{family.id}.imatrix.dat"
    if needs_build:
        source = _source_file(family, out / "sources.json")
        if family.imatrix and not imatrix.is_file():
            _run(
                [
                    str(imatrix_bin),
                    "-m",
                    str(source),
                    "-f",
                    str(calibration),
                    "-o",
                    str(imatrix),
                    "-c",
                    "512",
                    "--chunks",
                    "32",
                ]
            )
    files: dict[str, Path] = {"Q4_K_M": baseline}
    for quant in family.quants:
        if quant == "Q4_K_M":
            continue
        if quant in pinned:
            files[quant] = _registry_file(pinned[quant])
            continue
        files[quant] = _quant_file(family, quant, source, imatrix, quantize_bin)
    base_quality = _quality(out, family.id, "Q4_K_M", baseline, cli, perplexity, calibration)
    for quant, model in files.items():
        if quant == "Q4_K_M":
            quality = base_quality
        else:
            quality = _quality(out, family.id, quant, model, cli, perplexity, calibration)
        for kv in KV_TYPES:
            for context in CONTEXTS:
                rows = _cell(
                    rows,
                    out=out,
                    family=family.id,
                    quant=quant,
                    model=model,
                    kv=kv,
                    context=context,
                    cli=cli,
                    calibration=calibration,
                    quality=quality,
                    baseline=base_quality,
                )
    return rows


def _cell(
    rows: list[dict[str, object]],
    *,
    out: Path,
    family: str,
    quant: str,
    model: Path,
    kv: str,
    context: int,
    cli: Path,
    calibration: Path,
    quality: dict[str, float],
    baseline: dict[str, float],
) -> list[dict[str, object]]:
    key = f"{family}|{quant}|{kv}|{context}"
    previous = next(
        (
            row
            for row in rows
            if f"{row['model']}|{row['quant']}|{row['kv']}|{row['context']}" == key
        ),
        None,
    )
    if previous is not None and str(previous.get("status")) in {"completed", "over-budget"}:
        return rows
    prompt = calibration.read_text(encoding="utf-8")[:1200]
    try:
        log = _run(probe_command(cli, model, context=context, kv=kv, prompt=prompt))
        loaded = parse_load_log(log)
        prompt_tps, gen_tps = parse_tokens_per_second(log)
        status = "completed"
        error = ""
    except (PlotweaverError, subprocess.TimeoutExpired, OSError) as exc:
        loaded = None
        prompt_tps, gen_tps = 0.0, 0.0
        status = "error"
        error = str(exc)[:500]
    if loaded is None:
        row: dict[str, object] = {
            "model": family,
            "quant": quant,
            "kv": kv,
            "context": context,
            "flash_attn": True,
            "weight_bytes": 0,
            "kv_bytes": 0,
            "within_budget": False,
            "spilled": False,
            "perplexity": quality["perplexity"],
            "baseline_perplexity": baseline["perplexity"],
            "quality_loss": quality_loss(
                perplexity=quality["perplexity"],
                baseline_perplexity=baseline["perplexity"],
                synopsis_score=quality["synopsis_score"],
                baseline_synopsis_score=baseline["synopsis_score"],
            ),
            "refusal_rate": quality["refusal_rate"],
            "baseline_refusal": baseline["refusal_rate"],
            "synopsis_score": quality["synopsis_score"],
            "prompt_tps": prompt_tps,
            "gen_tps": gen_tps,
            "status": status,
            "error": error,
        }
    else:
        fits = within_budget(loaded.weight_bytes, loaded.kv_bytes, loaded.spilled)
        row = {
            "model": family,
            "quant": quant,
            "kv": kv,
            "context": context,
            "flash_attn": True,
            "weight_bytes": loaded.weight_bytes,
            "kv_bytes": loaded.kv_bytes,
            "within_budget": fits,
            "spilled": loaded.spilled,
            "perplexity": quality["perplexity"],
            "baseline_perplexity": baseline["perplexity"],
            "quality_loss": quality_loss(
                perplexity=quality["perplexity"],
                baseline_perplexity=baseline["perplexity"],
                synopsis_score=quality["synopsis_score"],
                baseline_synopsis_score=baseline["synopsis_score"],
            ),
            "refusal_rate": quality["refusal_rate"],
            "baseline_refusal": baseline["refusal_rate"],
            "synopsis_score": quality["synopsis_score"],
            "prompt_tps": prompt_tps,
            "gen_tps": gen_tps,
            "status": "completed" if fits else "over-budget",
            "error": "",
        }
    replaced = [
        item
        for item in rows
        if f"{item['model']}|{item['quant']}|{item['kv']}|{item['context']}" != key
    ]
    replaced.append(row)
    store_rows(out, replaced)
    return replaced


def _quality(
    out: Path,
    family: str,
    quant: str,
    model: Path,
    cli: Path,
    perplexity: Path,
    calibration: Path,
) -> dict[str, float]:
    cache = out / "quality.json"
    payload: dict[str, dict[str, float]] = {}
    if cache.is_file():
        loaded = read_json(cache)
        if isinstance(loaded, dict):
            payload = {str(key): value for key, value in loaded.items() if isinstance(value, dict)}
    name = f"{family}|{quant}"
    cached = payload.get(name)
    if cached is not None and "perplexity" in cached:
        return cached
    ppl_log = _run(
        [
            str(perplexity),
            "-m",
            str(model),
            "-f",
            str(calibration),
            "-c",
            "512",
            "--chunks",
            "4",
            "-fa",
            "on",
            "-ctk",
            "q8_0",
            "-ctv",
            "q8_0",
            "-ngl",
            "999",
            "--fit",
            "on",
            "--fit-target",
            str(FIT_TARGET_MIB),
        ]
    )
    refusals: list[str] = []
    for prompt in DARK_PROMPTS[:4]:
        refusals.append(_generate(cli, model, prompt))
    scores: list[float] = []
    for story in load_synopses()[:2]:
        text = _generate(cli, model, story.body[:800])
        scores.append(1.0 if len(text.strip()) >= 40 and refusal_rate([text]) == 0.0 else 0.0)
    result = {
        "perplexity": parse_perplexity(ppl_log),
        "refusal_rate": refusal_rate(refusals),
        "synopsis_score": sum(scores) / len(scores),
    }
    payload[name] = result
    write_json(cache, payload)
    return result


def _generate(cli: Path, model: Path, prompt: str) -> str:
    log = _run(probe_command(cli, model, context=8192, kv="q8_0", prompt=prompt))
    marker = "\n\n"
    if marker in log:
        return log.split(marker)[-1].strip()
    return log.strip()[-500:]


def _quant_file(
    family: Family,
    quant: str,
    source: Path,
    imatrix: Path,
    quantize_bin: Path,
) -> Path:
    dest = gguf_dir() / "fit16" / f"{family.id}-{quant}.gguf"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [str(quantize_bin), "--imatrix", str(imatrix), str(source), str(dest), quant]
    _run(command)
    return dest


def _registry_file(model_id: str) -> Path:
    for entry in load_registry(registry_path()):
        if entry.id == model_id:
            return download_model(entry)
    raise PlotweaverError(f"registry has no {model_id}")


def _source_file(family: Family, manifest: Path) -> Path:
    dest = gguf_dir() / "fit16-src" / family.source_filename
    if family.source_sha256 and dest.is_file():
        verify_file(dest, size=family.source_size, sha256=family.source_sha256)
        return dest
    known = _known_hash(manifest, family)
    if dest.is_file() and known and _sha256(dest) == known:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://huggingface.co/{family.repo}/resolve/{family.revision}/"
        f"{family.source_filename}?download=true"
    )
    partial = dest.with_suffix(dest.suffix + ".partial")
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(3600.0, connect=30.0),
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(1024 * 1024):
                handle.write(chunk)
    partial.replace(dest)
    if family.source_sha256:
        verify_file(dest, size=family.source_size, sha256=family.source_sha256)
        _remember_hash(manifest, family, family.source_sha256, family.source_size)
        return dest
    digest = _sha256(dest)
    if known and digest != known:
        dest.unlink()
        raise PlotweaverError(f"Q8 source hash changed for {family.source_filename}")
    _remember_hash(manifest, family, digest, dest.stat().st_size)
    return dest


def _known_hash(manifest: Path, family: Family) -> str:
    if not manifest.is_file():
        return ""
    payload = read_json(manifest)
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return ""
    for item in files:
        if isinstance(item, dict) and item.get("filename") == family.source_filename:
            return str(item.get("sha256") or "")
    return ""


def _remember_hash(manifest: Path, family: Family, digest: str, size: int) -> None:
    payload: dict[str, object] = {"files": []}
    if manifest.is_file():
        loaded = read_json(manifest)
        if isinstance(loaded, dict):
            payload = loaded
    files = payload.get("files")
    rows = [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []
    rows = [item for item in rows if item.get("filename") != family.source_filename]
    rows.append(
        {
            "repo": family.repo,
            "revision": family.revision,
            "filename": family.source_filename,
            "sha256": digest,
            "size": size,
        }
    )
    payload["files"] = rows
    write_json(manifest, payload)


def _sibling(server: Path, name: str) -> Path:
    for candidate in (server.with_name(name), server.with_name(name + ".exe")):
        if candidate.is_file():
            return candidate
    raise PlotweaverError(
        f"{name} from llama.cpp b11476 was not next to {server}. "
        "The Vulkan archive used by the bake-off includes these tools."
    )


def _run(command: list[str]) -> str:
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.TimeoutExpired as exc:
        raise PlotweaverError(f"timed out: {command[0]}") from exc
    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if proc.returncode != 0:
        raise PlotweaverError(output[-2000:])
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
