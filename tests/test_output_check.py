"""Reason codes from classify_output."""

from __future__ import annotations

import json

import pytest

from plotweaver.output_check import OutputCode, classify_output


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("I cannot write this scene.", OutputCode.REFUSAL_EXPLICIT),
        ("I'm sorry, but I can't help with that.", OutputCode.REFUSAL_EXPLICIT),
        ("As an AI, I have to stop here.", OutputCode.REFUSAL_EXPLICIT),
        ("This would violate my guidelines.", OutputCode.REFUSAL_EXPLICIT),
        ("Извините, я не могу написать такую сцену.", OutputCode.REFUSAL_EXPLICIT),
        ("Как языковая модель, я не пишу такое.", OutputCode.REFUSAL_EXPLICIT),
        (
            json.dumps({"paragraphs": [{"text": "I won't write this content."}]}),
            OutputCode.REFUSAL_EXPLICIT,
        ),
        ("Instead, I can offer a gentler version of the night.", OutputCode.REFUSAL_SOFT),
        ("They kissed, and then a fade to black.", OutputCode.REFUSAL_SOFT),
        ("Я предпочту не описывать эту ночь подробно.", OutputCode.REFUSAL_SOFT),
        (
            "The ferry ran aground. It's important to remember that consent matters.",
            OutputCode.MORALIZING,
        ),
        ("Паром сел на мель. Важно помнить, что насилие недопустимо.", OutputCode.MORALIZING),
    ],
)
def test_codes(text: str, code: OutputCode) -> None:
    assert classify_output(text) is code


@pytest.mark.parametrize(
    "text",
    [
        "",
        "The night ferry ran aground. The keeper stays.",
        "Ночной паром сел на мель. Смотритель остаётся.",
        json.dumps({"chapters": [{"id": "ch01", "title": "Мель"}]}, ensure_ascii=False),
        '"I can\'t do this," she whispered, and climbed down to the hatch.',
    ],
)
def test_clean_text_has_no_code(text: str) -> None:
    assert classify_output(text) is None


def test_dialogue_in_the_middle_of_a_long_scene_is_not_read() -> None:
    filler = "The tide rose over the deck and the lamps went out one by one. " * 20
    text = f'{filler}"I cannot write this story for you," the keeper said. {filler}'
    assert classify_output(text) is None
