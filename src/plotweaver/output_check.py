"""Reason codes for generation replies that do not do the task, and one retry.

``classify_output`` reads a reply and returns a code or ``None``.
``CheckedBackend`` wraps a backend: for plan, scene, and proofread calls it
classifies each reply, asks the same model once more on a hit, and records
the code so the run report, the CLI ``--json`` output, and the log can show it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from plotweaver.domain import Task
from plotweaver.errors import ModelOutputError
from plotweaver.jsontext import load_json_object
from plotweaver.llm import ChatMessage, Completion, LLMBackend, ModelSpec, task_of

_LOG = logging.getLogger("plotweaver.output_check")

_EDGE = 400


class OutputCode(StrEnum):
    """Why a reply was not used as written."""

    REFUSAL_EXPLICIT = "REFUSAL_EXPLICIT"
    REFUSAL_SOFT = "REFUSAL_SOFT"
    MORALIZING = "MORALIZING"


CHECKED_TASKS = frozenset(
    {
        Task.BIBLE,
        Task.OUTLINE,
        Task.BEATS,
        Task.DRAFT,
        Task.FILL,
        Task.REWRITE,
        Task.PROOFREAD,
    }
)

_EXPLICIT = re.compile(
    r"("
    r"\bi (?:can ?not|can't|can’t|won't|won’t|will not|am unable to|'m unable to|’m unable to"
    r"|am not able to|'m not able to) (?:help|assist|write|create|generate|produce|continue"
    r"|fulfil+|comply|provide|do)\b(?: (?:with|you))?(?: (?:this|that|your|such|the|a|an|any))?"
    r" (?:request|content|story|scene|material|text|task|prompt|kind)|"
    r"\bi (?:can ?not|can't|can’t|won't|won’t) (?:help|assist) with (?:that|this)\b|"
    r"\bi (?:must|have to|need to) (?:refuse|decline)\b|"
    r"\bi'?m sorry,? but i (?:can|won|will|am)|"
    r"\bas an ai\b|\bas a language model\b|\bas an ai language model\b|"
    r"\b(?:content|usage|safety) (?:policy|policies|guidelines)\b|"
    r"\bviolates? (?:my|the|our|openai'?s) (?:guidelines|policies|policy|rules)\b|"
    r"я не могу (?:помочь|написать|создать|сгенерировать|продолжить|выполнить|описать)|"
    r"не могу выполнить (?:этот|эту|ваш|вашу|такой|такую) (?:запрос|просьбу|задачу)|"
    r"как (?:языковая модель|ии|искусственный интеллект)\b|"
    r"я (?:должен|должна|вынужден|вынуждена) отказаться|"
    r"нарушает (?:мои|правила|политику)"
    r")",
    re.IGNORECASE,
)

_SOFT = re.compile(
    r"("
    r"\bi'?d (?:rather|prefer) not (?:to )?(?:write|describe|depict|go into|detail)\b|"
    r"\bi'?ll keep (?:it|this|the scene|things) (?:tasteful|non-explicit|implied|pg|vague)\b|"
    r"\binstead,? i (?:can|could|will|'ll) (?:offer|write|provide|suggest)\b|"
    r"\bhere (?:is|'s) a (?:toned[- ]down|tamer|softer|more tasteful|non-explicit) version\b|"
    r"\bfade to black\b|"
    r"\bsome things are better left unsaid\b|"
    r"я предпочту не (?:описывать|писать|вдаваться)|"
    r"вместо этого я (?:могу|предлагаю|напишу)|"
    r"в более (?:мягкой|сдержанной|корректной) форме|"
    r"дальше всё было прилично"
    r")",
    re.IGNORECASE,
)

_MORALIZING = re.compile(
    r"("
    r"\bit'?s (?:important|crucial|essential) to (?:remember|note|recognize|understand) that\b|"
    r"\bplease (?:remember|note|keep in mind) that\b|"
    r"\bconsent is (?:essential|important|crucial|key)\b|"
    r"\bif you or someone you know\b|"
    r"\bseek (?:professional )?help\b|"
    r"\b(?:trigger|content) warning\b|"
    r"\bthis (?:story|content|text|scene) (?:contains|depicts|deals with) "
    r"(?:sensitive|mature|disturbing)\b|"
    r"важно помнить,? что|"
    r"пожалуйста,? помните|"
    r"обратитесь (?:за помощью|к специалисту)|"
    r"предупреждение о содержании"
    r")",
    re.IGNORECASE,
)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _prose(text: str) -> str:
    parsed, _how = load_json_object(text)
    if parsed is None:
        return text
    return "\n".join(_strings(parsed))


def classify_output(text: str) -> OutputCode | None:
    """Return a reason code when the reply declines, waters down, or lectures.

    Only the start and the end of the reply are read, so dialogue inside a
    scene does not count.
    """
    prose = " ".join(_prose(text).split())
    if not prose:
        return None
    head = prose[:_EDGE]
    edges = head if len(prose) <= 2 * _EDGE else f"{head}\n{prose[-_EDGE:]}"
    if _EXPLICIT.search(head):
        return OutputCode.REFUSAL_EXPLICIT
    if _SOFT.search(edges):
        return OutputCode.REFUSAL_SOFT
    if _MORALIZING.search(edges):
        return OutputCode.MORALIZING
    return None


@dataclass(frozen=True)
class OutputEvent:
    """One flagged reply: the task, the code, and whether the retry was clean."""

    task: str
    code: str
    model_id: str
    retry_code: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _task(messages: list[ChatMessage]) -> Task | None:
    try:
        return task_of(messages)
    except ModelOutputError, ValueError:
        return None


class CheckedBackend:
    """Backend wrapper that retries a flagged plan, scene, or proofread reply once."""

    def __init__(self, inner: LLMBackend, *, log: Callable[[str], None] | None = None) -> None:
        self.inner = inner
        self.events: list[OutputEvent] = []
        self._log = log

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def load(self, spec: ModelSpec) -> None:
        self.inner.load(spec)

    def unload(self) -> None:
        self.inner.unload()

    def prepare_batch(self) -> None:
        self.inner.prepare_batch()

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_format: Mapping[str, object] | None = None,
    ) -> Completion:
        def ask() -> Completion:
            return self.inner.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                response_format=response_format,
            )

        first = ask()
        task = _task(messages)
        if task is None or task not in CHECKED_TASKS:
            return first
        code = classify_output(first.text)
        if code is None:
            return first
        self._say(f"{code.value} on {task.value} ({first.model_id}), retrying once")
        second = ask()
        again = classify_output(second.text)
        event = OutputEvent(task.value, code.value, first.model_id, again.value if again else None)
        self.events.append(event)
        if again is not None:
            self._say(f"{again.value} on {task.value} retry ({second.model_id})")
        return second

    def counts(self) -> dict[str, int]:
        """Flagged replies per reason code, first attempts only."""
        found: dict[str, int] = {}
        for event in self.events:
            found[event.code] = found.get(event.code, 0) + 1
        return found

    def _say(self, message: str) -> None:
        _LOG.warning("%s", message)
        if self._log is not None:
            self._log(message)
