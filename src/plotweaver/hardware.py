"""NVIDIA detection, the driver minimum, the suite VRAM budget, and the 83 C thermal rule.

The product refuses to start a real job without an NVIDIA RTX 40-series GPU or newer
(compute capability 8.9 or higher, and "RTX" in the device name). Tests set
PLOTWEAVER_FAKE_GPU instead of calling nvidia-smi.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from plotweaver.errors import GpuUnsupported
from plotweaver.ui.i18n import tr

NVIDIA_DRIVER_PAGE = "https://www.nvidia.com/Download/index.aspx"
# CUDA 12.8 GA on Linux and CUDA 12.4 GA on Windows, from the CUDA toolkit release notes.
MIN_DRIVER_LINUX = (570, 117)
MIN_DRIVER_WINDOWS = (551, 61)

# Ada (RTX 40) is compute capability 8.9. Anything older, including RTX 30 (8.6), is refused.
MIN_COMPUTE_CAP = 8.9
VRAM_HEADROOM_GB = 2.0
VRAM_HEADROOM_FRAC = 0.08
FULL_SPEED_S = 2.5 * 3600
HOT_C = 83.0
COOL_C = 75.0
THROTTLE_HOLD_S = 60.0
MEDIAN_WINDOW_S = 300.0
MAX_PAUSE_S = 600.0
PAUSE_STEP_S = 5.0
# nvidia-smi clocks throttle bits: SW thermal, HW thermal, HW power brake.
THROTTLE_BITS = 0x20 | 0x40 | 0x80
GB = 1024**3
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass(frozen=True)
class GpuInfo:
    """Name, compute capability, and memory of one NVIDIA GPU."""

    name: str
    compute_cap: float
    total_mib: float
    free_mib: float

    @property
    def total_gb(self) -> float:
        return self.total_mib / 1024

    @property
    def free_gb(self) -> float:
        return self.free_mib / 1024


def vram_headroom_gb(total_gb: float) -> float:
    """Leave at least 2 GB free, or 8 percent of the card when that is larger."""
    return max(VRAM_HEADROOM_GB, VRAM_HEADROOM_FRAC * max(0.0, total_gb))


def vram_budget_gb(free_gb: float, total_gb: float, fraction: float | None = None) -> float:
    """budget = free_now - max(2 GB, 8% of total). An optional fraction caps it further."""
    budget = max(0.0, free_gb - vram_headroom_gb(total_gb))
    if fraction is not None and 0 < fraction <= 1:
        budget = min(budget, fraction * total_gb)
    return budget


def _parse_fake(raw: str) -> GpuInfo | None:
    if raw.strip().lower() in {"", "none", "missing"}:
        return None
    name, cap, total, free = [part.strip() for part in raw.split(",")]
    return GpuInfo(name, float(cap), float(total), float(free))


def query_gpu() -> GpuInfo | None:
    """First NVIDIA GPU, or None when nvidia-smi is absent.

    PLOTWEAVER_FAKE_GPU is ``name,compute_cap,total_mib,free_mib`` or ``none``.
    """
    fake = os.environ.get("PLOTWEAVER_FAKE_GPU")
    if fake is not None:
        return _parse_fake(fake)
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,compute_cap,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError, subprocess.SubprocessError:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if proc.returncode != 0 or not line:
        return None
    parts = [part.strip() for part in line[0].split(",")]
    if len(parts) < 4:
        return None
    try:
        return GpuInfo(parts[0], float(parts[1]), float(parts[2]), float(parts[3]))
    except ValueError:
        return None


def is_supported(info: GpuInfo) -> bool:
    """RTX 40-series (Ada, sm_89) or a newer RTX card."""
    return info.compute_cap >= MIN_COMPUTE_CAP and "RTX" in info.name.upper()


@dataclass(frozen=True)
class DriverStatus:
    """Whether the installed NVIDIA driver can run the pinned CUDA runtime."""

    ok: bool
    version: str | None
    minimum: str
    message: str


def minimum_driver() -> tuple[int, ...]:
    """Driver tuple required by the CUDA build for this operating system."""
    if sys.platform == "win32":
        return MIN_DRIVER_WINDOWS
    return MIN_DRIVER_LINUX


def format_driver(parts: tuple[int, ...]) -> str:
    """Join a driver tuple the way nvidia-smi prints it."""
    return ".".join(str(part) for part in parts)


def parse_driver(text: str) -> tuple[int, ...]:
    """Leading integers from a driver version such as ``570.117``."""
    numbers: list[int] = []
    for piece in text.strip().split("."):
        digits: list[str] = []
        for char in piece:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            numbers.append(int("".join(digits)))
    return tuple(numbers)


def driver_meets(found: str, minimum: tuple[int, ...] | None = None) -> bool:
    """True when ``found`` is at least ``minimum`` (the platform CUDA floor by default)."""
    required = minimum_driver() if minimum is None else minimum
    got = parse_driver(found)
    if not got:
        return False
    width = max(len(got), len(required))
    left = got + (0,) * (width - len(got))
    right = required + (0,) * (width - len(required))
    return left >= right


def query_driver_version() -> str | None:
    """Installed NVIDIA driver, or None when nvidia-smi has nothing to report.

    ``PLOTWEAVER_FAKE_DRIVER`` is a version string, or ``none``.
    """
    fake = os.environ.get("PLOTWEAVER_FAKE_DRIVER")
    if fake is not None:
        if fake.strip().lower() in {"", "none", "missing"}:
            return None
        return fake.strip()
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip().splitlines()[0].strip() or None


def driver_status() -> DriverStatus:
    """Plain-language driver check, including NVIDIA's download page when it is too old."""
    required = minimum_driver()
    label = format_driver(required)
    found = query_driver_version()
    if found is None:
        return DriverStatus(
            False,
            None,
            label,
            tr("driver_missing").format(url=NVIDIA_DRIVER_PAGE),
        )
    if not driver_meets(found, required):
        return DriverStatus(
            False,
            found,
            label,
            tr("driver_old").format(version=found, minimum=label, url=NVIDIA_DRIVER_PAGE),
        )
    return DriverStatus(True, found, label, tr("driver_ok").format(version=found))


def driver_allows_cuda() -> bool:
    """True when the installed driver can run the pinned CUDA llama.cpp build."""
    return driver_status().ok


def require_supported_gpu() -> GpuInfo:
    """Return the GPU, or raise when it is not an RTX 40-series card or newer."""
    info = query_gpu()
    if info is None or not is_supported(info):
        found = info.name if info else "no NVIDIA GPU"
        cap = f", compute {info.compute_cap}" if info else ""
        raise GpuUnsupported(
            "Plotweaver needs an NVIDIA RTX 40-series GPU or newer "
            f"(compute capability {MIN_COMPUTE_CAP}+ and RTX in the name). "
            f"Found: {found}{cap}. Re-run with --mock for tests without a GPU."
        )
    return info


@dataclass(frozen=True)
class GpuSample:
    temp_c: float | None
    power_w: float | None
    throttle_mask: int


def read_nvidia_sample() -> GpuSample:
    """Temperature, power, and the throttle mask. Missing sensors come back empty."""
    fake = os.environ.get("PLOTWEAVER_FAKE_THERMAL")
    if fake is not None:
        # "temp,power,mask" or "none"
        if fake.strip().lower() == "none":
            return GpuSample(None, None, 0)
        temp_s, power_s, mask_s = [part.strip() for part in fake.split(",")]
        temp = None if temp_s in {"", "-"} else float(temp_s)
        power = None if power_s in {"", "-"} else float(power_s)
        return GpuSample(temp, power, int(mask_s, 0))
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,power.draw,clocks_throttle_reasons.active",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError, subprocess.SubprocessError:
        return GpuSample(None, None, 0)
    if proc.returncode != 0 or not proc.stdout.strip():
        return GpuSample(None, None, 0)
    parts = [part.strip() for part in proc.stdout.strip().splitlines()[0].split(",")]
    try:
        temp = float(parts[0])
        power = float(parts[1].split()[0])
        mask = int(parts[2], 16)
    except ValueError, IndexError:
        return GpuSample(None, None, 0)
    return GpuSample(temp, power, mask)


class ThermalGuard:
    """Full speed for 2.5 hours, then pause while the 5-minute median stays at 83 C or above.

    A throttle bit held for more than 60 seconds also pauses. Work resumes at 75 C with the
    throttle clear. A missing sensor never pauses the job.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self.t0 = now()
        self._temps: deque[tuple[float, float]] = deque()
        self._throttle_since: float | None = None
        self.temp: float | None = None
        self.power: float | None = None
        self.mask = 0

    def elapsed(self, now: float | None = None) -> float:
        current = self._now() if now is None else now
        return current - self.t0

    def update(self, sample: GpuSample, now: float | None = None) -> None:
        current = self._now() if now is None else now
        self.temp = sample.temp_c
        self.power = sample.power_w
        self.mask = sample.throttle_mask
        if sample.temp_c is not None:
            self._temps.append((current, sample.temp_c))
        cutoff = current - MEDIAN_WINDOW_S
        while self._temps and self._temps[0][0] < cutoff:
            self._temps.popleft()
        if self.mask & THROTTLE_BITS:
            if self._throttle_since is None:
                self._throttle_since = current
        else:
            self._throttle_since = None

    def median_c(self) -> float | None:
        if not self._temps:
            return None
        return float(statistics.median(temp for _, temp in self._temps))

    def throttle_seconds(self, now: float | None = None) -> float:
        if self._throttle_since is None:
            return 0.0
        current = self._now() if now is None else now
        return max(0.0, current - self._throttle_since)

    def should_pause(self, now: float | None = None) -> bool:
        current = self._now() if now is None else now
        if self.elapsed(current) < FULL_SPEED_S:
            return False
        median = self.median_c()
        if median is not None and median >= HOT_C:
            return True
        return self.throttle_seconds(current) > THROTTLE_HOLD_S

    def cool_enough(self) -> bool:
        throttling = self._throttle_since is not None
        median = self.median_c()
        if median is None:
            return not throttling
        return median <= COOL_C and not throttling

    def pause_after_batch(
        self,
        sample: Callable[[], GpuSample] = read_nvidia_sample,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = lambda _message: None,
    ) -> float:
        """Sample and, when the rule says so, sleep until the card is cool or 10 minutes pass."""
        self.update(sample())
        median = self.median_c()
        if self.temp is not None or self.mask:
            shown = "-" if median is None else f"{median:.0f}"
            log(f"GPU 5-min median {shown} C, throttle mask {self.mask:#x}")
        if not self.should_pause():
            return 0.0
        log(f"cooling pause (5-min median {median if median is not None else '-'} C)")
        paused = 0.0
        while paused < MAX_PAUSE_S:
            sleep(PAUSE_STEP_S)
            paused += PAUSE_STEP_S
            self.update(sample())
            if self.cool_enough():
                log(f"cooling pause ended after {paused:.0f} s")
                return paused
        log(f"cooling pause stopped after {paused:.0f} s")
        return paused
