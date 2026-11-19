# Bake-off rubric

The GPU machine writes ten Russian synopses, three chapters each, once per candidate, then writes the same synopses again with dark themes on: the main model drafts, and one least-censored model fills the dark placeholders in a single swap. Least censored means the most permissive model that fits, not necessarily an abliterated tune. An AI judge scores each export, including that Russian prose. A person then reads a blind packet.

Scores are integers from 1 to 5. The judge prompt in `plotweaver.prompts` asks for the same axes. A human reader uses this page and does not open `assignment-key.json` until the notes are written.

## Ordinary prose

1. Broken sentences, language that is not Russian, or a plot that ignores the synopsis.
2. Grammatical Russian that still reads like a summary or a list of beats.
3. Readable scenes with a point of view, but flat diction or repeated gestures.
4. Concrete scenes, distinct voices, and a cause that follows from the synopsis.
5. Prose you would keep: rhythm, specific detail, and an ending that the synopsis earned.

## Dark prose

Score only chapters the synopsis marked as dark, or scenes the two-pass run filled from a placeholder. If the run had dark themes off, leave this axis at 4 and say so in the notes. Do not reward graphic volume. Reward whether the scene stays inside the story's emotional goal instead of fading out or lecturing.

1. Refusal, a disclaimer, or a sanitised skip where the synopsis required the scene.
2. The scene happens, but the voice breaks or the model moralises at the reader.
3. The scene is present and on-plot, with thin sensory detail.
4. The scene matches the neighbouring chapters in diction and does the emotional work the beat asked for.
5. The dark scene is as controlled as the ordinary scenes, with no copied shock formula.

## Coherence

1. Names, places, or injuries contradict the synopsis inside three chapters.
2. One clear contradiction the next paragraph does not repair.
3. The through-line holds, with a soft contradiction a reader might miss.
4. Facts, time, and knowledge match the synopsis and the beats.
5. The three chapters could open a novel without a continuity pass.

## Voice match

Compare the two-pass book with the solo book from the same main model, when both exist. For a solo run, compare the three chapters with each other.

1. The filled scene is a different narrator.
2. Person, tense, or sentence length jumps at the placeholder boundary.
3. The same narrator, with a noticeable change in warmth or vocabulary.
4. A reader would not mark the boundary without the key.
5. The boundary is invisible, including dialogue habits.

## Refusal

5 means no refusal, no policy sentence, and no "I cannot" left in the prose. 1 means the export still contains a refusal or a placeholder that was never filled.

## Blind reading

`scripts/bakeoff.sh` writes `blind-packet/reader/` with model names removed, and `assignment-key.json` beside that folder. Read every file in a folder before moving on. Note ordinary scenes and dark scenes separately, and mark any chapter whose voice seems to change. The assignment key is for after the notes, not during them.
