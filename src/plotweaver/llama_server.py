"""llama.cpp llama-server as a worker process. One large model at a time.

The binary is not vendored. The bake-off script downloads llama.cpp b11476
(Vulkan), the same build Audiobook Builder pins. Tests use the mock backend
and never start this process.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import signal
import socket
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

import httpx

from plotweaver.errors import PlotweaverError
from plotweaver.gguf import block_and_experts
from plotweaver.hardware import query_gpu, vram_budget_gb, vram_short_message
from plotweaver.llm import ChatMessage, Completion, ModelSpec
from plotweaver.paths import suite_state_dir
from plotweaver.vram_plan import ServerPlan, plan_server

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
_JOB_KILL_ON_CLOSE = 0x2000
_JOB_EXTENDED_LIMIT = 9


class _JobBasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def llama_pidfile() -> Path:
    """Pid of the llama-server this app started, under the suite state directory."""
    return suite_state_dir() / "llama-server.pid"


def stop_owned_server() -> bool:
    """Stop a llama-server recorded in the suite pidfile. Other processes are left alone."""
    path = llama_pidfile()
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except OSError, ValueError:
        path.unlink(missing_ok=True)
        return False
    if pid <= 0 or not _is_llama_server(pid):
        path.unlink(missing_ok=True)
        return False
    _kill_pid_tree(pid)
    path.unlink(missing_ok=True)
    return True


def _write_pidfile(pid: int) -> None:
    path = llama_pidfile()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _clear_pidfile(pid: int) -> None:
    path = llama_pidfile()
    if not path.is_file():
        return
    try:
        current = int(path.read_text(encoding="utf-8").strip())
    except OSError, ValueError:
        path.unlink(missing_ok=True)
        return
    if current == pid:
        path.unlink(missing_ok=True)


def _is_llama_server(pid: int) -> bool:
    name = _process_name(pid).lower()
    return "llama-server" in name


def _process_name(pid: int) -> str:
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=_NO_WINDOW,
            )
        except OSError, subprocess.SubprocessError:
            return ""
        text = proc.stdout or ""
        if text.startswith('"'):
            return text.split('"', 2)[1]
        return text.strip()
    comm = Path(f"/proc/{pid}/comm")
    try:
        return comm.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _kill_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            check=False,
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return


def _arm_kill_on_close(proc: subprocess.Popen[str]) -> int | None:
    """Windows job object that kills the server when this process handle closes."""
    if os.name != "nt":
        return None
    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return None
    kernel = windll("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel.SetInformationJobObject.restype = ctypes.c_int
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.AssignProcessToJobObject.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JobExtendedLimit()
    info.BasicLimitInformation.LimitFlags = _JOB_KILL_ON_CLOSE
    if not kernel.SetInformationJobObject(
        job, _JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)
    ):
        kernel.CloseHandle(job)
        return None
    handle = getattr(proc, "_handle", None)
    if not handle or not kernel.AssignProcessToJobObject(job, int(handle)):
        kernel.CloseHandle(job)
        return None
    return int(job)


def _close_job(handle: int | None) -> None:
    if not handle or os.name != "nt":
        return
    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return
    kernel = windll("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle(handle)


def apply_vram_budget_cap(budget_gb: float) -> float:
    """Cap the server budget when PLOTWEAVER_VRAM_BUDGET_CAP_GB is set."""
    raw = os.environ.get("PLOTWEAVER_VRAM_BUDGET_CAP_GB", "").strip()
    if not raw:
        return budget_gb
    try:
        cap = float(raw)
    except ValueError:
        return budget_gb
    if cap <= 0:
        return budget_gb
    return min(budget_gb, cap)


def append_completion_metric(
    *,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    seconds: float,
) -> None:
    """Append one JSON line when PLOTWEAVER_METRICS points at a file."""
    raw = os.environ.get("PLOTWEAVER_METRICS", "").strip()
    if not raw:
        return
    rate = (completion_tokens / seconds) if seconds > 0 else 0.0
    line = json.dumps(
        {
            "model": model_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "seconds": round(seconds, 4),
            "tokens_per_second": round(rate, 4),
            "ts": time.time(),
        }
    )
    try:
        with open(raw, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return


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
        self._job: int | None = None
        atexit.register(self.unload)
        stop_owned_server()

    def load(self, spec: ModelSpec) -> None:
        if self._proc is not None and self.model_id == spec.id and not self._halved:
            return
        self.unload()
        stop_owned_server()
        if not spec.path.is_file():
            raise PlotweaverError(f"GGUF not found: {spec.path}")
        if not self.binary.is_file():
            raise PlotweaverError(
                f"llama-server not found at {self.binary}. "
                "On the GPU machine, run scripts/bakeoff.sh so it can download llama.cpp b11476."
            )
        gpu = query_gpu()
        if gpu is None:
            raise PlotweaverError("llama-server needs a visible NVIDIA GPU.")
        budget = apply_vram_budget_cap(vram_budget_gb(gpu.free_gb, gpu.total_gb))
        weight_gb = spec.path.stat().st_size / (1024**3)
        if weight_gb > gpu.free_gb:
            raise PlotweaverError(vram_short_message())
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
        pid = proc.pid if proc is not None else None
        if proc is not None and proc.poll() is None and pid is not None:
            _kill_pid_tree(pid)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        _close_job(self._job)
        self._job = None
        if pid is not None:
            _clear_pidfile(pid)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_format: Mapping[str, object] | None = None,
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
        if response_format is not None:
            payload["response_format"] = dict(response_format)
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Prose calls use a low temperature from the runner; planning stays higher.
        # Thinking stays off for the process (see _start). Qwen templates also honour this.
        payload["chat_template_kwargs"] = {"enable_thinking": temperature >= 0.7}
        url = f"http://127.0.0.1:{self._port}/v1/chat/completions"
        started = time.perf_counter()
        try:
            response = httpx.post(url, json=payload, timeout=httpx.Timeout(1200.0, connect=10.0))
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise PlotweaverError(f"llama-server request failed: {exc}") from exc
        elapsed = time.perf_counter() - started
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
        append_completion_metric(
            model_id=self.model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed,
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
        self._job = _arm_kill_on_close(proc)
        _write_pidfile(proc.pid)
        self._proc = proc
        deadline = time.monotonic() + 300
        health = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = ""
                if proc.stdout is not None:
                    output = proc.stdout.read()[:2000]
                self.unload()
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
        self.unload()
        raise PlotweaverError("llama-server did not become healthy")
