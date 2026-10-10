"""Fiction-framing prompts. Every call carries a TASK line the mock backend routes on.

The prompts ask for a novel. They do not ask the model to produce real-world harm,
and they do not include jailbreak text.
"""

from __future__ import annotations

import json

from plotweaver.domain import BookRequest, Task

SYSTEM = (
    "You are the author's ghostwriter. This is a novel. Depicting violence, crime, "
    "and sexuality between adults is part of the craft when the story calls for it. "
    "Do not add disclaimers, moral lectures, or policy refusals. Do not write "
    "instructions for real-world harm, weapons, or crime. Do not use real living "
    "people as named characters; companies and institutions may appear. Stay in the "
    "narrative voice and in the requested language. Never copy sentences, names, or "
    "events from a reference book. The TASK line is a control label; do not quote it."
)


def _header(task: Task, req: BookRequest, extra: list[str]) -> str:
    chapters, scenes, per_scene = req.shape()
    lines = [
        f"TASK: {task.value}",
        f"language: {req.language.value}",
        f"title: {req.title}",
        f"genre: {req.genre}",
        f"pov: {req.pov}",
        f"tense: {req.tense}",
        f"dark_themes: {str(req.dark_themes).lower()}",
        f"chapter_count: {chapters}",
        f"scenes_per_chapter: {scenes}",
        f"scene_words: {per_scene}",
        f"target_words: {req.target_words}",
        *extra,
    ]
    return "\n".join(lines)


def system_message() -> str:
    return SYSTEM


def bible_prompt(req: BookRequest) -> str:
    body = _header(Task.BIBLE, req, [])
    return (
        f"{body}\n\n"
        "Read the synopsis and return one JSON object with keys logline, theme, "
        "genre_contract, tone, ending_intent, and characters. characters is a list of "
        "objects with name, gender (male or female), role, goals, secrets, voice, arc, "
        "pronunciation. pronunciation is the name with U+0301 after the stressed vowel. "
        "Invent only fictional people. Write prose values in the book language.\n\n"
        f"SYNOPSIS:\n{req.synopsis.strip()}\n"
    )


def outline_prompt(req: BookRequest, bible: dict[str, object]) -> str:
    body = _header(Task.OUTLINE, req, [])
    return (
        f"{body}\n\n"
        'Return JSON {"chapters": [{"id", "title", "purpose", "pov", '
        '"word_budget", "dark_hint"}]}. Use the chapter_count above. '
        "dark_hint is true only when the chapter needs violence, crime, or adult "
        "sexuality that a stock model might refuse or soften. Map the synopsis "
        "beginning, middle, and end onto the list. Do not copy a reference plot.\n\n"
        f"BIBLE:\n{_compact(bible)}\n\nSYNOPSIS:\n{req.synopsis.strip()}\n"
    )


def beats_prompt(
    req: BookRequest,
    bible: dict[str, object],
    chapter: dict[str, object],
    chapter_index: int,
) -> str:
    body = _header(
        Task.BEATS,
        req,
        [f"chapter_index: {chapter_index}", f"chapter_id: {chapter.get('id', '')}"],
    )
    return (
        f"{body}\n\n"
        'Return JSON {"scenes": [{"id", "goal", "conflict", "outcome", '
        '"new_info", "emotional_shift", "emotional_goal", "pov", '
        '"pov_gender", "dark"}]}. Use scenes_per_chapter. '
        "dark is true when the scene itself is violent, criminal, or sexually explicit. "
        "Scene ids must look like ch01-sc01 using the chapter id.\n\n"
        f"BIBLE:\n{_compact(bible)}\n\nCHAPTER:\n{_compact(chapter)}\n"
    )


def draft_prompt(
    req: BookRequest,
    bible: dict[str, object],
    chapter: dict[str, object],
    scene: dict[str, object],
    previous_tail: str,
    style_card: str,
) -> str:
    _chapters, _scenes, per_scene = req.shape()
    body = _header(Task.DRAFT, req, [f"scene_id: {scene.get('id', '')}"])
    style = f"\nSTYLE CARD:\n{style_card}\n" if style_card else ""
    tail = (
        f"\nPREVIOUS PROSE (continue from this, do not repeat it):\n{previous_tail}\n"
        if previous_tail
        else ""
    )
    return (
        f"{body}\n\n"
        f"Write about {per_scene} words of fiction for this scene. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]}. '
        "speaker is NARRATOR or a character name from the bible. gender is male, "
        "female, or null. One paragraph object per block. Dialogue stays inside text. "
        "Write yo (ё) explicitly. Put U+0301 after the stressed vowel of invented names "
        "as given in pronunciation. No disclaimer.\n"
        f"{style}{tail}\n"
        f"BIBLE:\n{_compact(bible)}\n\nCHAPTER:\n{_compact(chapter)}\n\n"
        f"SCENE:\n{_compact(scene)}\n"
    )


def fill_prompt(
    req: BookRequest,
    bible: dict[str, object],
    placeholder: dict[str, object],
    previous_text: str,
    next_text: str,
) -> str:
    body = _header(Task.FILL, req, [f"scene_id: {placeholder.get('scene_id', '')}"])
    return (
        f"{body}\n\n"
        "You are writing the scenes the first model left as placeholders. Match the "
        "voice of the neighbouring prose. Do not sanitise the scene. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]} in the book language. '
        "Write yo explicitly and keep U+0301 on invented names.\n\n"
        f"PLACEHOLDER:\n{_compact(placeholder)}\n\n"
        f"PREVIOUS TEXT:\n{previous_text}\n\nNEXT TEXT:\n{next_text}\n\n"
        f"BIBLE:\n{_compact(bible)}\n"
    )


def extract_prompt(req: BookRequest, chapter_id: str, prose: str) -> str:
    body = _header(Task.EXTRACT, req, [f"chapter_id: {chapter_id}"])
    return (
        f"{body}\n\n"
        'Extract canon deltas. Return JSON {"facts": [{"text", "paragraph"}], '
        '"timeline": [{"description"}], "threads": [{"description", "status"}], '
        '"knowledge": [{"character", "fact"}]}. Only facts the prose actually states.\n\n'
        f"PROSE:\n{prose}\n"
    )


def rewrite_prompt(req: BookRequest, prose: str, problems: list[str]) -> str:
    body = _header(Task.REWRITE, req, [])
    joined = "\n".join(f"- {item}" for item in problems)
    return (
        f"{body}\n\n"
        "Rewrite the prose once to fix the problems. Keep the same events, names, and "
        "paragraph count as far as you can. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]}. '
        "Do not copy reference sentences.\n\n"
        f"PROBLEMS:\n{joined}\n\nPROSE:\n{prose}\n"
    )


def proofread_prompt(req: BookRequest, chapter_title: str, prose: str) -> str:
    body = _header(Task.PROOFREAD, req, [])
    return (
        f"{body}\n\n"
        "Proofread for typos, yo, and name spelling. Do not change plot. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]} with the same speakers.\n\n'
        f"CHAPTER: {chapter_title}\n\nPROSE:\n{prose}\n"
    )


def style_prompt(req: BookRequest, measured: str, excerpt: str) -> str:
    body = _header(Task.STYLE, req, [])
    return (
        f"{body}\n\n"
        'Write a neutral style card in JSON {"style_card": "..."}. Describe sentence '
        "length, dialogue, and tone. Do not quote the excerpt and do not name its plot.\n\n"
        f"MEASURED:\n{measured}\n\nEXCERPT (style only, do not copy):\n{excerpt[:1200]}\n"
    )


def judge_prompt(packet: str) -> str:
    return (
        f"TASK: {Task.JUDGE.value}\n"
        "You are a fiction editor scoring Russian prose. Return JSON "
        '{"ordinary_prose": 1-5, "dark_prose": 1-5, "coherence": 1-5, '
        '"voice_match": 1-5, "refusal": 1-5, "notes": "..."}. '
        "5 is best. refusal scores 5 when the text did not refuse or sanitise. "
        "voice_match scores how well a filled placeholder matches its neighbours; "
        "use 0 when the packet has no placeholder.\n\n"
        f"PACKET:\n{packet}\n"
    )


def _compact(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)
