"""llama.cpp llama-server as a worker process. One large model at a time.

The binary is not vendored. The bake-off script downloads a CUDA build; tests use
the mock backend and never start this process.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx

from plotweaver.errors import PlotweaverError
from plotweaver.gguf import block_and_experts
from plotweaver.hardware import query_gpu, vram_budget_gb
from plotweaver.llm import ChatMessage, Completion, ModelSpec
from plotweaver.vram_plan import ServerPlan, plan_server

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LlamaServer:
    """OpenAI-compatible worker. load() stops any model already running."""

    def __init__(self, binary: Path) -> None:
        self.binary = binary
        self.model_id = ""
        self._proc: subprocess.Popen[str] | None = None
        self._port = 0
        self._spec: ModelSpec | None = None
        self._plan: ServerPlan | None = None
        self._halved = False

    def load(self, spec: ModelSpec) -> None:
        if self._proc is not None and self.model_id == spec.id and not self._halved:
            return
        self.unload()
        if not spec.path.is_file():
            raise PlotweaverError(f"GGUF not found: {spec.path}")
        if not self.binary.is_file():
            raise PlotweaverError(
                f"llama-server not found at {self.binary}. "
                "On the GPU machine, run scripts/bakeoff.sh so it can download the binary."
            )
        gpu = query_gpu()
        if gpu is None:
            raise PlotweaverError("llama-server needs a visible NVIDIA GPU.")
        budget = vram_budget_gb(gpu.free_gb, gpu.total_gb)
        weight_gb = spec.path.stat().st_size / (1024**3)
        blocks, experts = block_and_experts(spec.path)
        if spec.moe and experts <= 0:
            experts = 1
        desired = spec.context
        plan = plan_server(
            weight_gb=weight_gb,
            budget_gb=budget,
            total_gb=gpu.total_gb,
            block_count=blocks,
            expert_count=experts,
            desired_ctx=desired,
        )
        if self._halved:
            plan = ServerPlan(
                n_gpu_layers=plan.n_gpu_layers,
                context=max(4096, plan.context // 2),
                fit_target_mib=plan.fit_target_mib,
                n_cpu_moe=plan.n_cpu_moe,
                cache_type="q4_0",
                batch=max(64, plan.batch // 2),
                ubatch=max(64, plan.ubatch // 2),
                spilled=True,
            )
        self._start(spec, plan)

    def prepare_batch(self) -> None:
        """Re-measure. If we are inside the headroom, reload once with a smaller context."""
        gpu = query_gpu()
        if gpu is None or self._spec is None or self._halved:
            return
        if gpu.free_gb < (self._plan.fit_target_mib / 1024 if self._plan else 2):
            self._halved = True
            self.load(self._spec)

    def unload(self) -> None:
        proc = self._proc
        self._proc = None
        self.model_id = ""
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                check=False,
                capture_output=True,
                creationflags=_NO_WINDOW,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Completion:
        if self._proc is None or self._port == 0:
            raise PlotweaverError("llama-server is not running")
        payload: dict[str, object] = {
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "top_p": 0.95,
            "min_p": 0.05,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Prose calls use a low temperature from the runner; planning stays higher.
        # Thinking stays off for the process (see _start). Qwen templates also honour this.
        payload["chat_template_kwargs"] = {"enable_thinking": temperature >= 0.7}
        url = f"http://127.0.0.1:{self._port}/v1/chat/completions"
        try:
            response = httpx.post(url, json=payload, timeout=httpx.Timeout(1200.0, connect=10.0))
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise PlotweaverError(f"llama-server request failed: {exc}") from exc
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise PlotweaverError("llama-server returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        text = ""
        if isinstance(message, dict):
            text = str(message.get("content") or "")
        usage = body.get("usage") if isinstance(body, dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0) if isinstance(usage, dict) else 0
        completion_tokens = (
            int(usage.get("completion_tokens") or 0) if isinstance(usage, dict) else 0
        )
        return Completion(text, prompt_tokens, completion_tokens, self.model_id)

    def _start(self, spec: ModelSpec, plan: ServerPlan) -> None:
        port = _free_port()
        command = [
            str(self.binary),
            "-m",
            str(spec.path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            str(plan.context),
            "-ngl",
            str(plan.n_gpu_layers),
            "--fit",
            "on",
            "--fit-target",
            str(plan.fit_target_mib),
            "--fit-ctx",
            str(min(4096, plan.context)),
            "-ctk",
            plan.cache_type,
            "-ctv",
            plan.cache_type,
            "-b",
            str(plan.batch),
            "-ub",
            str(plan.ubatch),
            "--temp",
            "0.8",
            "--min-p",
            "0.05",
            "--top-p",
            "0.95",
            "--dry-multiplier",
            "0.8",
            "--dry-base",
            "1.75",
            "--dry-allowed-length",
            "2",
            "--jinja",
            "--reasoning",
            "off",
            "-np",
            "1",
        ]
        if plan.n_cpu_moe:
            command.extend(["--n-cpu-moe", str(plan.n_cpu_moe)])
        if os.name == "nt":
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        else:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        deadline = time.monotonic() + 300
        health = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = ""
                if proc.stdout is not None:
                    output = proc.stdout.read()[:2000]
                raise PlotweaverError(f"llama-server exited early: {output}")
            try:
                probe = httpx.get(health, timeout=2.0)
                if probe.status_code == 200:
                    self._proc = proc
                    self._port = port
                    self._spec = spec
                    self._plan = plan
                    self.model_id = spec.id
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        proc.kill()
        raise PlotweaverError("llama-server did not become healthy")
