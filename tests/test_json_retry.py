"""Lenient JSON repair and the one grammar retry."""

from __future__ import annotations

import json
import logging

import pytest

from plotweaver.errors import ModelOutputError
from plotweaver.jsontext import parse_json_object
from plotweaver.llm import JSON_SCHEMA_FORMAT, ChatMessage, Completion, MockBackend, complete_json


def test_trailing_comma_and_fence_parse() -> None:
    assert parse_json_object('```json\n{"ok": true,}\n```') == {"ok": True}
    assert parse_json_object('note before {"a": 1, "b": [2,],}') == {"a": 1, "b": [2]}


def test_grammar_retry_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Once:
        model_id = "retry"

        def __init__(self) -> None:
            self.formats: list[object] = []

        def load(self, spec: object) -> None:
            del spec

        def unload(self) -> None:
            return None

        def prepare_batch(self) -> None:
            return None

        def complete(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float,
            max_tokens: int,
            json_mode: bool,
            response_format: object = None,
        ) -> Completion:
            del messages, temperature, max_tokens, json_mode
            self.formats.append(response_format)
            if response_format is None:
                return Completion("not json", 1, 1, "retry")
            return Completion(json.dumps({"kept": True}), 1, 1, "retry")

    backend = _Once()
    with caplog.at_level(logging.INFO, logger="plotweaver.llm"):
        assert complete_json(
            backend,
            [ChatMessage("user", "TASK: probe")],
            temperature=0.2,
            max_tokens=32,
        ) == {"kept": True}
    assert backend.formats[1] == JSON_SCHEMA_FORMAT
    assert "json_schema" in caplog.text


def test_repaired_path_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    class _Fenced:
        model_id = "fenced"

        def load(self, spec: object) -> None:
            del spec

        def unload(self) -> None:
            return None

        def prepare_batch(self) -> None:
            return None

        def complete(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float,
            max_tokens: int,
            json_mode: bool,
            response_format: object = None,
        ) -> Completion:
            del messages, temperature, max_tokens, json_mode, response_format
            return Completion('Sure.\n```json\n{"ok": true,}\n```', 1, 1, "fenced")

    with caplog.at_level(logging.INFO, logger="plotweaver.llm"):
        assert complete_json(
            _Fenced(),
            [ChatMessage("user", "TASK: probe")],
            temperature=0.2,
            max_tokens=32,
        ) == {"ok": True}
    assert "repaired" in caplog.text


def test_two_failures_raise() -> None:
    class _Bad:
        model_id = "bad"

        def load(self, spec: object) -> None:
            del spec

        def unload(self) -> None:
            return None

        def prepare_batch(self) -> None:
            return None

        def complete(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float,
            max_tokens: int,
            json_mode: bool,
            response_format: object = None,
        ) -> Completion:
            del messages, temperature, max_tokens, json_mode, response_format
            return Completion("still no", 1, 1, "bad")

    with pytest.raises(ModelOutputError):
        complete_json(
            _Bad(),
            [ChatMessage("user", "TASK: probe")],
            temperature=0.2,
            max_tokens=8,
        )


def test_mock_still_returns_json(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="plotweaver.llm"):
        parsed = complete_json(
            MockBackend(),
            [ChatMessage("user", "TASK: bible\nlanguage: en")],
            temperature=0.4,
            max_tokens=200,
        )
    assert "logline" in parsed
    assert "json_object" in caplog.text
