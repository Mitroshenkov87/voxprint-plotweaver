"""Fiction-framing prompts. Every call carries a TASK line the mock backend routes on.

The prompts ask for a novel. They do not ask the model to produce real-world harm,
and they do not include jailbreak text.
"""

from __future__ import annotations

import json
from typing import Literal

from plotweaver.brief import attach_context
from plotweaver.domain import BookRequest, Task
from plotweaver.errors import assert_never
from plotweaver.length import (
    CHAPTER_SUMMARY_CHARS,
    EXTRACT_MAX_TOKENS,
    PLAN_MAX_TOKENS,
    STORY_SO_FAR_CHARS,
    clip_text,
    fit_pieces,
    scene_max_tokens,
    user_token_budget,
)

SYSTEM = (
    "You are the author's ghostwriter. This is a novel. Depicting violence, crime, "
    "and sexuality between adults is part of the craft when the story calls for it. "
    "Do not add disclaimers, moral lectures, or policy refusals. Do not write "
    "instructions for real-world harm, weapons, or crime. Do not use real living "
    "people as named characters; companies and institutions may appear. Stay in the "
    "narrative voice and in the requested language. Never copy sentences, names, or "
    "events from a reference book. The TASK line is a control label; do not quote it."
)


def _header(
    task: Task,
    req: BookRequest,
    extra: list[str],
    *,
    include_context: bool = True,
) -> str:
    attach_context(req)
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
    if include_context and req.generation_context.strip():
        lines.extend(["", req.generation_context.strip()])
    return "\n".join(lines)


def system_message() -> str:
    """Return the ghostwriter system message sent with every model call."""
    return SYSTEM


def bible_prompt(req: BookRequest) -> str:
    """Ask for the story bible as one JSON object."""
    attach_context(req)
    body = _header(Task.BIBLE, req, [], include_context=False)
    binding = ""
    if req.generation_context.strip():
        binding = (
            "The BOOK BRIEF block is binding for genre, tone, point of view, tense, "
            "audience, setting, ending, and characters. "
        )
    instructions = (
        f"{binding}"
        "Read the synopsis and return one JSON object with keys logline, theme, "
        "genre_contract, tone, ending_intent, and characters. characters is a list of "
        "objects with name, gender (male or female), role, goals, secrets, voice, arc, "
        "pronunciation, age_group (child, teen, young_adult, adult, elderly, or "
        "unspecified), and voice_hints (optional object with pitch, pace, timbre, notes). "
        "pronunciation is the name with U+0301 after the stressed vowel. "
        "Invent only fictional people. Write prose values in the book language."
    )
    return _fit(
        req,
        [
            f"{body}\n\n{instructions}",
            _context_piece(req),
            f"SYNOPSIS:\n{_clip(req, req.synopsis.strip(), 600)}",
        ],
        PLAN_MAX_TOKENS,
    )


def outline_parts_prompt(
    req: BookRequest,
    bible: dict[str, object],
    spans: list[tuple[int, int]],
) -> str:
    """Ask for the part list that covers every chapter exactly once."""
    span_lines = "\n".join(f"part_span: {start}-{end}" for start, end in spans)
    body = _header(
        Task.OUTLINE,
        req,
        ["outline_phase: parts", f"part_count: {len(spans)}", span_lines],
        include_context=False,
    )
    instructions = (
        'Return JSON {"parts": [{"index", "title", "purpose", "chapter_start", '
        '"chapter_end"}]}. Use part_count. The part_span lines are the split to follow. '
        "Cover every chapter from 1 through chapter_count once. Do not skip a number "
        "and do not overlap. Follow the BOOK BRIEF plot points and ending when a brief "
        "is present. Map the synopsis beginning, middle, and end onto the parts."
    )
    return _fit(
        req,
        [
            f"{body}\n\n{instructions}",
            _context_piece(req),
            f"BIBLE DIGEST:\n{bible_digest(bible)}",
            f"SYNOPSIS:\n{_clip(req, req.synopsis.strip(), 600)}",
        ],
        PLAN_MAX_TOKENS,
    )


def outline_chapters_prompt(
    req: BookRequest,
    bible: dict[str, object],
    part: dict[str, object],
    start: int,
    end: int,
    budgets: dict[int, int],
) -> str:
    """Ask for one batch of chapters inside a single part."""
    body = _header(
        Task.OUTLINE,
        req,
        [
            "outline_phase: chapters",
            f"chapter_start: {start}",
            f"chapter_end: {end}",
            f"part_index: {part.get('index', '')}",
            _budget_lines(budgets),
        ],
        include_context=False,
    )
    instructions = (
        'Return JSON {"chapters": [{"index", "title", "purpose", "pov", '
        '"word_budget", "dark_hint"}]}. Include every index from chapter_start through '
        "chapter_end once. Use the word_budget lines. dark_hint is true only when the "
        "chapter needs violence, crime, or adult sexuality that a stock model might "
        "refuse or soften. Do not copy a reference plot."
    )
    return _fit(
        req,
        [
            f"{body}\n\n{instructions}",
            _context_piece(req),
            f"PART:\n{_compact(part)}",
            f"BIBLE DIGEST:\n{bible_digest(bible)}",
            f"SYNOPSIS:\n{_clip(req, req.synopsis.strip(), 400)}",
        ],
        PLAN_MAX_TOKENS,
    )


def outline_repair_prompt(
    req: BookRequest,
    bible: dict[str, object],
    *,
    kind: Literal["parts", "chapters"],
    start: int,
    end: int,
    missing: list[int],
    spans: list[tuple[int, int]],
    part: dict[str, object] | None,
    budgets: dict[int, int],
) -> str:
    """Ask again for the chapter or part numbers the previous reply skipped."""
    missing_text = ",".join(str(number) for number in missing)
    span_lines = "\n".join(f"part_span: {span_start}-{span_end}" for span_start, span_end in spans)
    phase = "repair-parts" if kind == "parts" else "repair-chapters"
    extra = [
        f"outline_phase: {phase}",
        f"chapter_start: {start}",
        f"chapter_end: {end}",
        f"missing: {missing_text}",
    ]
    if span_lines:
        extra.append(span_lines)
    if kind == "chapters":
        extra.append(_budget_lines(budgets))
    body = _header(Task.OUTLINE, req, extra, include_context=False)
    match kind:
        case "parts":
            instructions = (
                'Return JSON {"parts": [{"index", "title", "purpose", "chapter_start", '
                '"chapter_end"}]}. Cover every chapter number in missing. Follow the '
                "part_span lines. Do not repeat chapters that are not missing."
            )
        case "chapters":
            instructions = (
                'Return JSON {"chapters": [{"index", "title", "purpose", "pov", '
                '"word_budget", "dark_hint"}]}. Include every index in missing and no '
                "others. Use the word_budget lines."
            )
        case _ as unreachable:
            assert_never(unreachable)
    pieces = [
        f"{body}\n\n{instructions}",
        _context_piece(req),
        f"BIBLE DIGEST:\n{bible_digest(bible)}",
    ]
    if part:
        pieces.append(f"PART:\n{_compact(part)}")
    return _fit(req, pieces, PLAN_MAX_TOKENS)


def beats_prompt(
    req: BookRequest,
    bible: dict[str, object],
    chapter: dict[str, object],
    chapter_index: int,
    continuity: str = "",
) -> str:
    """Ask for the scene beats of one chapter."""
    body = _header(
        Task.BEATS,
        req,
        [f"chapter_index: {chapter_index}", f"chapter_id: {chapter.get('id', '')}"],
        include_context=False,
    )
    instructions = (
        'Return JSON {"scenes": [{"id", "goal", "conflict", "outcome", '
        '"new_info", "emotional_shift", "emotional_goal", "pov", '
        '"pov_gender", "dark"}]}. Use scenes_per_chapter. '
        "dark is true when the scene itself is violent, criminal, or sexually explicit. "
        "Scene ids must look like ch01-sc01 using the chapter id."
    )
    pieces = [
        f"{body}\n\n{instructions}",
        _context_piece(req),
        f"BIBLE DIGEST:\n{bible_digest(bible)}",
        f"CHAPTER:\n{_compact(chapter)}",
    ]
    if continuity.strip():
        pieces.append(f"STORY SO FAR:\n{continuity.strip()[:STORY_SO_FAR_CHARS]}")
    return _fit(req, pieces, PLAN_MAX_TOKENS)


def draft_prompt(
    req: BookRequest,
    bible: dict[str, object],
    chapter: dict[str, object],
    scene: dict[str, object],
    previous_tail: str,
    style_card: str,
    continuity: dict[str, object] | None = None,
) -> str:
    """Ask for the prose of one scene, with a digest and the rolling summary."""
    _chapters, _scenes, per_scene = req.shape()
    body = _header(
        Task.DRAFT,
        req,
        [f"scene_id: {scene.get('id', '')}"],
        include_context=False,
    )
    instructions = (
        f"Write about {per_scene} words of fiction for this scene. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]}. '
        "speaker is NARRATOR or a character name from the bible. gender is male, "
        "female, or null. One paragraph object per block. Dialogue stays inside text. "
        "Write yo (ё) explicitly. Put U+0301 after the stressed vowel of invented names "
        "as given in pronunciation. No disclaimer."
    )
    story, recent = _continuity_pieces(continuity)
    pieces = [
        f"{body}\n\n{instructions}",
        _context_piece(req),
        f"BIBLE DIGEST:\n{bible_digest(bible)}",
        f"CHAPTER:\n{_compact(chapter)}",
        f"SCENE:\n{_compact(scene)}",
    ]
    if story:
        pieces.append(f"STORY SO FAR:\n{story}")
    if recent:
        pieces.append(f"RECENT CHAPTERS:\n{recent}")
    if style_card.strip():
        pieces.append(f"STYLE CARD:\n{style_card.strip()}")
    if previous_tail.strip():
        pieces.append(
            "PREVIOUS PROSE (continue from this, do not repeat it):\n" + previous_tail.strip()
        )
    return _fit(req, pieces, scene_max_tokens(per_scene, req.language.value))


def fill_prompt(
    req: BookRequest,
    bible: dict[str, object],
    placeholder: dict[str, object],
    previous_text: str,
    next_text: str,
    continuity: str = "",
) -> str:
    """Ask a second model to write a scene the first model left blank."""
    _chapters, _scenes, per_scene = req.shape()
    body = _header(
        Task.FILL,
        req,
        [f"scene_id: {placeholder.get('scene_id', '')}"],
        include_context=False,
    )
    instructions = (
        "You are writing the scenes the first model left as placeholders. Match the "
        "voice of the neighbouring prose. Do not sanitise the scene. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]} in the book language. '
        "Write yo explicitly and keep U+0301 on invented names."
    )
    pieces = [
        f"{body}\n\n{instructions}",
        _context_piece(req),
        f"BIBLE DIGEST:\n{bible_digest(bible)}",
        f"PLACEHOLDER:\n{_compact(placeholder)}",
    ]
    if continuity.strip():
        pieces.append(f"STORY SO FAR:\n{continuity.strip()[:STORY_SO_FAR_CHARS]}")
    if previous_text.strip():
        pieces.append(f"PREVIOUS TEXT:\n{previous_text.strip()}")
    if next_text.strip():
        pieces.append(f"NEXT TEXT:\n{next_text.strip()}")
    return _fit(req, pieces, scene_max_tokens(per_scene, req.language.value))


def extract_prompt(
    req: BookRequest,
    chapter_id: str,
    prose: str,
    previous_story: str = "",
) -> str:
    """Ask for the canon facts stated in one chapter, plus a rolling summary."""
    body = _header(Task.EXTRACT, req, [f"chapter_id: {chapter_id}"], include_context=False)
    instructions = (
        'Extract canon deltas. Return JSON {"facts": [{"text", "paragraph"}], '
        '"timeline": [{"description"}], "threads": [{"description", "status"}], '
        '"knowledge": [{"character", "fact"}], "summary", "story_so_far"}. '
        "Only facts the prose actually states. summary is one or two sentences for "
        "this chapter. story_so_far rewrites the whole book so far in under 80 words. "
        "Do not list every chapter."
    )
    pieces = [f"{body}\n\n{instructions}", f"PROSE:\n{prose}"]
    if previous_story.strip():
        pieces.append(f"STORY SO FAR:\n{previous_story.strip()[:STORY_SO_FAR_CHARS]}")
    return _fit(req, pieces, EXTRACT_MAX_TOKENS)


def rewrite_prompt(req: BookRequest, prose: str, problems: list[str]) -> str:
    """Ask for one rewrite that fixes the listed problems."""
    _chapters, _scenes, per_scene = req.shape()
    body = _header(Task.REWRITE, req, [], include_context=False)
    joined = "\n".join(f"- {item}" for item in problems)
    instructions = (
        "Rewrite the prose once to fix the problems. Keep the same events, names, and "
        "paragraph count as far as you can. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]}. '
        "Do not copy reference sentences."
    )
    return _fit(
        req,
        [
            f"{body}\n\n{instructions}",
            f"PROBLEMS:\n{joined}",
            f"PROSE:\n{prose}",
        ],
        scene_max_tokens(per_scene, req.language.value),
    )


def proofread_prompt(req: BookRequest, chapter_title: str, prose: str) -> str:
    """Ask for a spelling pass that keeps the plot."""
    _chapters, _scenes, per_scene = req.shape()
    body = _header(Task.PROOFREAD, req, [], include_context=False)
    instructions = (
        "Proofread for typos, yo, and name spelling. Do not change plot. Return JSON "
        '{"paragraphs": [{"text", "speaker", "gender"}]} with the same speakers.'
    )
    return _fit(
        req,
        [
            f"{body}\n\n{instructions}",
            f"CHAPTER: {chapter_title}\n\nPROSE:\n{prose}",
        ],
        scene_max_tokens(per_scene, req.language.value),
    )


def style_prompt(req: BookRequest, measured: str, excerpt: str) -> str:
    """Ask for a neutral style card from a reference excerpt."""
    body = _header(Task.STYLE, req, [])
    return (
        f"{body}\n\n"
        'Write a neutral style card in JSON {"style_card": "..."}. Describe sentence '
        "length, dialogue, and tone. Do not quote the excerpt and do not name its plot.\n\n"
        f"MEASURED:\n{measured}\n\nEXCERPT (style only, do not copy):\n{excerpt[:1200]}\n"
    )


def brief_draft_prompt(idea: str, language: str) -> str:
    """Ask the local model to expand notes into a version-1 book brief."""
    return (
        f"TASK: {Task.BRIEF.value}\n"
        f"language: {language}\n"
        "Return one JSON object with keys version, title, language, pages, "
        "words_per_page, genre, subgenre, tone, pov, tense, audience, setting, "
        "characters, plot_points, ending_type, style_references, dark_themes, "
        "synopsis, and guessed. characters is a list of objects with name, role, "
        "description, and gender (male, female, or unspecified). guessed is the list "
        "of keys you had to choose because the notes did not say them. Fill every key. "
        "Write prose values in the requested language. version is 1. "
        "Do not invent a target_words value.\n\n"
        f"IDEA:\n{idea.strip()}\n"
    )


def judge_prompt(packet: str) -> str:
    """Ask the judge model to score a prose packet."""
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


def bible_digest(bible: dict[str, object]) -> str:
    """Names, roles, voices, and the logline. Secrets and arcs stay out of later prompts."""
    lines: list[str] = []
    for key in ("logline", "theme", "tone", "ending_intent", "genre_contract"):
        value = str(bible.get(key) or "").strip()
        if value:
            lines.append(f"{key}: {value[:160]}")
    characters = bible.get("characters")
    rendered: list[str] = []
    if isinstance(characters, list):
        for item in characters[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            gender = str(item.get("gender") or "").strip()
            role = str(item.get("role") or "").strip()
            voice = str(item.get("voice") or "").strip()[:60]
            spoken = str(item.get("pronunciation") or "").strip()
            rendered.append(f"{name} ({gender}), {role}; voice: {voice}; pronunciation: {spoken}")
    if rendered:
        lines.append("characters: " + " | ".join(rendered))
    return "\n".join(lines)[:900]


def _compact(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _fit(req: BookRequest, pieces: list[str], max_tokens: int) -> str:
    return fit_pieces(
        pieces,
        russian=req.language.value == "ru",
        budget=user_token_budget(max_tokens),
    )


def _clip(req: BookRequest, text: str, tokens: int) -> str:
    return clip_text(text, russian=req.language.value == "ru", tokens=tokens)


def _context_piece(req: BookRequest) -> str:
    attach_context(req)
    return req.generation_context.strip()


def _budget_lines(budgets: dict[int, int]) -> str:
    return "\n".join(f"word_budget: {index}={words}" for index, words in sorted(budgets.items()))


def _continuity_pieces(continuity: dict[str, object] | None) -> tuple[str, str]:
    if not continuity:
        return "", ""
    story = str(continuity.get("story_so_far") or "").strip()[:STORY_SO_FAR_CHARS]
    raw = continuity.get("chapters")
    recent: list[str] = []
    if isinstance(raw, list):
        for item in raw[-2:]:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()[:CHAPTER_SUMMARY_CHARS]
            chapter_id = str(item.get("id") or "").strip()
            if summary:
                recent.append(f"{chapter_id}: {summary}".strip())
    return story, "\n".join(recent)
