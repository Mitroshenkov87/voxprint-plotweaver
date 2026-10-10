"""Errors the CLI turns into a non-zero exit."""

from typing import Never


class PlotweaverError(Exception):
    """Expected failure: missing GPU, bad project, model output we will not invent."""


class GpuUnsupported(PlotweaverError):
    """The machine has no NVIDIA RTX 40-series (or newer) GPU."""


class ModelOutputError(PlotweaverError):
    """The loaded model did not return a usable reply. The step is not checkpointed."""


def assert_never(value: Never) -> Never:
    """Exhaustiveness guard for enums and unions."""
    raise RuntimeError(f"unhandled variant: {value!r}")
