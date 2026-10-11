"""Model call types and JSON completion with one grammar retry."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from plotweaver.domain import Task
from plotweaver.errors import ModelOutputError
from plotweaver.jsontext import load_json_object

_LOG = logging.getLogger("plotweaver.llm")
JSON_SCHEMA_FORMAT: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "plotweaver_object",
        "strict": False,
        "schema": {"type": "object", "additionalProperties": True},
    },
}


@dataclass
class ChatMessage:
    """One message in a model chat."""

    role: str
    content: str


@dataclass
class Completion:
    """Text and token counts from one model reply."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str


@dataclass
class ModelSpec:
    """One GGUF the worker may load. Only one large model is resident at a time."""

    id: str
    path: Path
    context: int = 8192
    license: str = "Apache-2.0"
    moe: bool = False


class LLMBackend(Protocol):
    """The model caller the pipeline uses."""

    model_id: str

    def load(self, spec: ModelSpec) -> None:
        """Load this model, unloading any other large model first."""

    def unload(self) -> None:
        """Drop the resident model so the next load is the only one in memory."""

    def prepare_batch(self) -> None:
        """Re-measure VRAM before a batch. The mock does nothing."""

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_format: Mapping[str, object] | None = None,
    ) -> Completion:
        """One non-streaming completion."""


def task_of(messages: list[ChatMessage]) -> Task:
    """Read the TASK line from the latest user message."""
    for message in reversed(messages):
        if message.role != "user":
            continue
        for line in message.content.splitlines():
            if line.startswith("TASK:"):
                return Task(line.split(":", 1)[1].strip())
    raise ModelOutputError("prompt has no TASK line")


def complete_json(
    backend: LLMBackend,
    messages: list[ChatMessage],
    *,
    temperature: float,
    max_tokens: int,
) -> dict[str, object]:
    """Ask for JSON. One grammar retry, then a lenient repair, then fail.

    The log line names the path that succeeded: ``json_object``, ``repaired``,
    ``json_schema``, or ``json_schema-repaired``.
    """
    first = backend.complete(
        messages, temperature=temperature, max_tokens=max_tokens, json_mode=True
    )
    parsed, how = load_json_object(first.text)
    if parsed is not None:
        _LOG.info("JSON step succeeded via %s", "repaired" if how == "repaired" else "json_object")
        return parsed
    second = backend.complete(
        messages,
        temperature=0.2,
        max_tokens=max_tokens,
        json_mode=True,
        response_format=JSON_SCHEMA_FORMAT,
    )
    parsed, how = load_json_object(second.text)
    if parsed is None:
        raise ModelOutputError("the model did not return JSON")
    label = "json_schema" if how == "plain" else "json_schema-repaired"
    _LOG.info("JSON step succeeded via %s", label)
    return parsed
