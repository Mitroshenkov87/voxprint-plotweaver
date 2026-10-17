# Writing a brief

A book brief is the set of choices the generator keeps: title, length, genre, point of view, tense, audience, setting, characters, plot points, ending, and synopsis. You can fill it by hand, paste a finished brief, or start from messy notes.

The same fields are on the new-book screen and in `plotweaver run --brief`.

## Help me write the brief

1. Write the notes in the notes box. Fragments are enough.
2. Press **Help me write the brief**. The local model fills every field. With **Mock model** checked, a fixed sample is used instead.
3. Fields the notes did not state are marked **Guessed**. Change any of them. The mark goes away when you edit that field.
4. Read point of view and tense. They stay visible on the form.
5. Open **Prompt preview** if you want to see the block that will be sent with the book. Edit that text when you want those sentences used instead of the compiled fields.
6. Press **Write the book** when the brief looks right.

`plotweaver brief draft --idea "..."` does the same expansion from the command line. Add `--json` for the object, or `--dry-run` to print the plan without calling a model.

## Copy prompt for any AI chat

**Copy prompt for any AI chat** puts a self-contained prompt on the clipboard. Paste it into another assistant, then paste that assistant's reply back with **Paste brief**. The reply must be the Markdown template below, or the same fields as JSON. Headings stay in English. Prose can be in the book language.

A bad paste names the field. A missing title, language, genre, point of view, tense, synopsis, or character is rejected. So is a language other than `en` or `ru`, a gender other than `male`, `female`, or `unspecified`, and a target word count that is not pages times words per page.

## A filled example

```markdown
# Book brief

version: 1

## Title

Station

## Language

en

## Length

pages: 40
words_per_page: 250
chapters:
scenes_per_chapter:

## Genre

science fiction

## Subgenre

expedition

## Tone

dry

## Point of view

third-person limited

## Tense

past

## Audience

adult

## Setting

a research station

## Characters

- name: Ilya
  role: commander
  description: Short orders.
  gender: male

## Plot points

- The seal fails.
- The crew stays.

## Ending

bittersweet

## Style references

- a field log

## Dark themes

no

## Synopsis

The seal on the station fails. The crew stays and keeps the log.

## Guessed

- tone
- audience
- ending
```

Leave `chapters` and `scenes_per_chapter` empty to derive them. At 250 words per page, 40 pages is 10,000 words. The automatic chapter count for that length is 8, with 2 scenes per chapter. Up to about 600 pages the planner keeps 2 or 3 scenes and targets about 1,000 to 1,500 words in each scene when the chapter is long enough. A short chapter stays at 2 scenes even when each one is under 1,000 words. Past about 600 pages, Russian scenes shrink so one draft call can finish them. Type a chapter count when you want a different split. The longest length that is structurally within budget (mock-tested) is 2,000 pages. Prose quality at that length, including scenes of about 1,000 words and the 700-character rolling summary, has not been checked on a real model. The window's length chips are 25, 80, 250, and 550 pages.

## A good brief and a weak one

A good brief names the people, the place, the turn, and the ending, and it says the point of view and the tense. The synopsis agrees with those fields.

A weak brief is only a mood ("something sad in space") or a synopsis that implies a different narrator than the point-of-view field. The generator is told to keep the fields, so a mismatch shows up as a book that ignores the synopsis or a synopsis that ignores the fields. Make them agree before you start.

## Length

Words are pages times words per page. On the window the length chips are a story (25 pages), a novella (80), and a novel (250, the default and the ceiling). The long-novel chip (~500–600 pages) stays on the row and is switched off: very long books arrive in the next update. The free field and Expert pages accept 1 to 250. At 250 they say this is as long as this update can write. The line under the chips shows pages, words, and a reading time at 250 words per minute. These are planning labels, not measured run times.

A longer book is more chapters only until the ceiling. Empty `chapters` uses `min(40, max(8, round(words / 2500)))`. Scenes per chapter default to 2. Words per scene are `max(400, words // (chapters × scenes))`.

| Pages | Words at 250 per page | Chapters if left empty | Words asked per scene (2 scenes) |
| --- | --- | --- | --- |
| 25 | 6,250 | 8, the floor | 400, the floor (16 × 400 is 6,400 words) |
| 80 | 20,000 | 8 | 1,250 |
| 250 | 62,500 | 25 | 1,250 |
| 550 | 137,500 | 40, the ceiling (an uncapped split would be 55) | 1,718 |

Expert can set chapters from 0 to 40 and scenes per chapter from 1 to 8. Words per page stay between 100 and 600. Pages stop at 2,000.

The window stops at 250 pages because that is the longest book these calls reliably finish at 250 words a page and 2 scenes a chapter. 250 pages is 25 chapters. An indented outline of 25 short chapter purposes is about 1,900 tokens and fits in 2,048. 26 chapters almost fill that call. Each scene call stops at 4,096 tokens (`min(4096, max(512, words_per_scene × 3))`). 25 chapters × 2 scenes ask for 1,250 words, and the runner budgets 3,750 tokens, which fits. A 550-page book is 40 chapters (the ceiling; an uncapped split would be 55) and about 1,718 words a scene. That scene budget is 5,154 tokens and is cut at 4,096. A 40-chapter outline is past 2,048 tokens as well. The command line can still ask for more words; those same caps apply, and the window does not offer that length. A scene prompt carries the bible, that chapter, that scene, and the last 1,500 characters of the previous scene. It does not carry the rest of the book. When VRAM is tight the model context is halved and does not go below 4,096.

The 16 GB tier uses the smaller stock model and keeps 2 GB free. The 24 GB tier uses the larger stock model and keeps 3 GB free. The larger model does more work per call, so a 24 GB card is not a shortcut to a shorter wait for the same page count. A long run can pause while the card is hot and resume when it cools.

## Tips

- Check every **Guessed** mark before you start. Those values were filled in because the notes were silent.
- Point of view and tense are binding. "Third-person limited" and "past" are the defaults when a draft has to choose.
- One character needs a name. Role, a short description, and gender (`male`, `female`, or `unspecified`) go with it.
- Plot points are one per line. They are the turns you want kept, not a scene list.
- Dark themes off keeps the stock model on every scene. On, a later pass fills scenes marked dark when a least-censored model is installed.
- If you edit the prompt preview, that text replaces the compiled brief for the whole run.
