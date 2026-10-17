"""Chapter and scene budgets for a target length.

Outline replies stay inside 2,048 tokens. A scene reply stays inside 4,096.
Russian is budgeted at a Gemma-class rate, the tighter of the 16 GB and 24 GB
tokenisers. A spilled context on either tier is 4,096 tokens, so the prompt and
the completion share that window.

2,000 pages at 250 words per page is the longest book this budget can keep
consistent. The rolling summary is a fixed size. Past that length the same
digest is spread over more plot than it can hold. Calls for a longer book still
fit; they are outside the length treated as reliable. A ceiling of 400 chapters
stops a runaway page count from queuing tens of thousands of calls.
"""

from __future__ import annotations

PLAN_MAX_TOKENS = 2048
SCENE_MAX_TOKENS = 4096
EXTRACT_MAX_TOKENS = 1024
CONTEXT_FLOOR = 4096
SYSTEM_TOKEN_RESERVE = 320
PROOF_INSTRUCTION_TOKENS = 250
RELIABLE_MAX_PAGES = 2000
MIN_CHAPTERS = 8
MIN_WORDS_PER_CHAPTER = 2500
MAX_WORDS_PER_CHAPTER = 4000
TARGET_WORDS_PER_CHAPTER = 3200
SAFETY_CHAPTER_CEILING = 400
RU_TOKENS_PER_WORD = 4
EN_TOKENS_PER_WORD = 2
OUTLINE_TOKENS_PER_CHAPTER = 180
OUTLINE_USABLE_TOKENS = 1600
STORY_SO_FAR_CHARS = 700
CHAPTER_SUMMARY_CHARS = 240

_PROOF_MARGIN = 80
_COMPLETION_PAD = 48


def tokens_per_word(language: str) -> int:
    """Output tokens one word is assumed to cost. English is the looser rate."""
    if language == "en":
        return EN_TOKENS_PER_WORD
    return RU_TOKENS_PER_WORD


def estimate_tokens(text: str, *, russian: bool) -> int:
    """Rough token count. Russian is estimated at two characters per token."""
    if not text:
        return 0
    divisor = 2 if russian else 4
    return (len(text) + divisor - 1) // divisor


def chapter_count_for(target_words: int) -> int:
    """Chapters for a word target. Short books stay at eight; long ones stay in band."""
    words = max(0, target_words)
    count = (words + TARGET_WORDS_PER_CHAPTER // 2) // TARGET_WORDS_PER_CHAPTER
    count = max(MIN_CHAPTERS, count)
    count = _grow_to_band(words, count)
    while count > MIN_CHAPTERS and _words_each(words, count) < MIN_WORDS_PER_CHAPTER:
        count -= 1
    return _grow_to_band(words, count)


def chapters_per_outline_call() -> int:
    """How many chapter objects fit in one 2,048-token outline reply."""
    return max(1, OUTLINE_USABLE_TOKENS // OUTLINE_TOKENS_PER_CHAPTER)


def scene_word_cap(language: str) -> int:
    """Words one scene may request and still survive a proofread round trip."""
    rate = tokens_per_word(language)
    overhead = SYSTEM_TOKEN_RESERVE + PROOF_INSTRUCTION_TOKENS + _COMPLETION_PAD + _PROOF_MARGIN
    room = CONTEXT_FLOOR - overhead
    if room <= 0:
        return 200
    return max(200, (room * 4) // (rate * 9))


def scene_max_tokens(words: int, language: str) -> int:
    """Completion cap for one scene. Never above 4,096, and the prompt keeps room."""
    rate = tokens_per_word(language)
    needed = (max(1, words) * rate * 5) // 4 + _COMPLETION_PAD
    room = max(512, CONTEXT_FLOOR - SYSTEM_TOKEN_RESERVE - 256)
    return min(SCENE_MAX_TOKENS, max(512, needed), room)


def user_token_budget(max_tokens: int) -> int:
    """Tokens left for the user message beside the system reserve and the completion."""
    completion = min(max(0, max_tokens), CONTEXT_FLOOR)
    return max(256, CONTEXT_FLOOR - SYSTEM_TOKEN_RESERVE - completion)


def plan_shape(
    target_words: int,
    language: str,
    chapter_count: int | None,
    scenes_per_chapter: int | None,
    scene_words: int | None = None,
) -> tuple[int, int, int]:
    """Return chapters, scenes per chapter, and words per scene.

    An explicit chapter count is kept. Scene count is at least the requested
    number, and higher when a scene would not fit the draft budget. An explicit
    ``scene_words`` value is clamped to that budget and does not add scenes.
    """
    words = max(1, target_words)
    if chapter_count is not None and chapter_count > 0:
        chapters = chapter_count
    else:
        chapters = chapter_count_for(words)
    if scenes_per_chapter is None:
        minimum = 2
    else:
        minimum = max(1, scenes_per_chapter)
    cap = scene_word_cap(language)
    if scene_words is not None and scene_words > 0:
        return chapters, minimum, min(max(1, scene_words), cap)
    per_chapter = max(1, words // chapters)
    needed = max(1, (per_chapter + cap - 1) // cap)
    scenes = max(minimum, needed)
    per_scene = max(1, words // (chapters * scenes))
    while per_scene > cap:
        scenes += 1
        per_scene = max(1, words // (chapters * scenes))
    return chapters, scenes, per_scene


def chapter_word_budgets(target_words: int, chapters: int) -> list[int]:
    """Split the word target across chapters. Earlier chapters take the remainder."""
    count = max(1, chapters)
    words = max(0, target_words)
    base, extra = divmod(words, count)
    return [base + (1 if index < extra else 0) for index in range(count)]


def scaled_scene_count(chapter_words: int, existing: int, word_cap: int) -> int:
    """Scene count for one chapter, at least ``existing`` and at most one budget each."""
    have = max(0, existing)
    if word_cap <= 0:
        return max(1, have)
    needed = max(1, (max(1, chapter_words) + word_cap - 1) // word_cap)
    return max(have, needed, 1)


def clip_text(text: str, *, russian: bool, tokens: int) -> str:
    """Cut ``text`` so the token estimate is at most ``tokens``."""
    if tokens <= 0 or not text:
        return ""
    if estimate_tokens(text, russian=russian) <= tokens:
        return text
    divisor = 2 if russian else 4
    clipped = text[: tokens * divisor].rstrip()
    while clipped and estimate_tokens(clipped, russian=russian) > tokens:
        clipped = clipped[: max(0, len(clipped) - divisor)].rstrip()
    return clipped


def fit_pieces(pieces: list[str], *, russian: bool, budget: int) -> str:
    """Join prompt pieces so the estimate stays within ``budget`` tokens.

    The first piece is kept intact so the TASK line stays. Later pieces are
    shortened from the end.
    """
    if not pieces:
        return ""
    required = pieces[0]
    rest = [piece for piece in pieces[1:]]

    def total(parts: list[str]) -> int:
        body = "\n\n".join(part for part in [required, *parts] if part.strip())
        return estimate_tokens(body, russian=russian)

    while rest and total(rest) > budget:
        last = rest[-1]
        if len(last) <= 48:
            rest.pop()
            continue
        rest[-1] = last[: max(48, len(last) // 2)].rstrip()
    return "\n\n".join(part for part in [required, *rest] if part.strip())


def call_fits(
    text: str,
    *,
    russian: bool,
    max_tokens: int,
    instruction_tokens: int = PROOF_INSTRUCTION_TOKENS,
) -> bool:
    """True when the reserved prompt, the text, and the completion share the floor."""
    prompt = SYSTEM_TOKEN_RESERVE + instruction_tokens + estimate_tokens(text, russian=russian)
    return prompt + max_tokens <= CONTEXT_FLOOR


def _words_each(words: int, count: int) -> int:
    if count <= 0:
        return words
    return words // count


def _grow_to_band(words: int, count: int) -> int:
    while count < SAFETY_CHAPTER_CEILING and _words_each(words, count) > MAX_WORDS_PER_CHAPTER:
        count += 1
    return count
