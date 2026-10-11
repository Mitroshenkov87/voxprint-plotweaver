"""Load the dev-only mock backend when the dev extra is installed."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from plotweaver.errors import PlotweaverError
from plotweaver.llm import LLMBackend

_factory: Callable[[], LLMBackend] | None = None
try:
    from plotweaver_dev.mock import MockBackend as _LoadedMock

    def _make() -> LLMBackend:
        return cast(LLMBackend, _LoadedMock())

    _factory = _make
except ImportError:
    _factory = None


def mock_backend() -> LLMBackend:
    """Return the deterministic mock, or say that the dev extra is required."""
    if _factory is None:
        raise PlotweaverError(
            "--mock is not included in this install. "
            'Install the dev extra: pip install "voxprint-plotweaver[dev]".'
        )
    return _factory()
