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

Words are pages times words per page. On the window the length chips are a story (25 pages), a novella (80), a novel (250, the default), and a long novel (550). The free field and Expert pages accept any count from 1 to 2,000 and write the same page count. Above 600 pages the window shows a plain note: very long books are written as short scenes, and quality is still being checked. The line under the chips shows pages, words, and a reading time at 250 words per minute. These are planning labels, not measured run times.

Empty `chapters` follows the planner: at least 8 chapters, about 3,200 words a chapter, kept between 2,500 and 4,000. Scene count starts at 2 and rises so each scene fits one draft. English scenes stay near 750 words. Russian scenes stay near 377 words. An explicit chapter count is kept. An explicit scene count is a minimum; the planner still adds scenes when one would be too long.

| Pages | Words at 250 per page | Chapters if left empty | English scenes × words | Russian scenes × words |
| --- | --- | --- | --- | --- |
| 25 | 6,250 | 8 | 2 × 390 | 3 × 260 |
| 80 | 20,000 | 8 | 4 × 625 | 7 × 357 |
| 250 | 62,500 | 20 | 5 × 625 | 9 × 347 |
| 550 | 137,500 | 43 | 5 × 639 | 9 × 355 |
| 2,000 | 500,000 | 156 | 5 × 641 | 9 × 356 |

Expert chapters run from 0 to 400. Zero follows the planner. Words per page stay between 100 and 600. Pages stop at 2,000.

2,000 pages is the longest length that is structurally within budget (mock-tested). Outline chapters are written in batches that fit a 2,048-token reply, and each scene is sized for a 4,096-token draft. Prose quality past about 550 pages, including Russian scenes of about 377 words and the 700-character rolling summary, has not been checked on a real model. A scene prompt carries a compact bible digest and a rolling story summary, plus the tail of the previous scene when it fits. It does not carry the rest of the book. When VRAM is tight the model context is halved and does not go below 4,096.

The 16 GB tier uses the smaller stock model and keeps 2 GB free. The 24 GB tier uses the larger stock model and keeps 3 GB free. The larger model does more work per call, so a 24 GB card is not a shortcut to a shorter wait for the same page count. A long run can pause while the card is hot and resume when it cools.

## Tips

- Check every **Guessed** mark before you start. Those values were filled in because the notes were silent.
- Point of view and tense are binding. "Third-person limited" and "past" are the defaults when a draft has to choose.
- One character needs a name. Role, a short description, and gender (`male`, `female`, or `unspecified`) go with it.
- Plot points are one per line. They are the turns you want kept, not a scene list.
- Dark themes off keeps the stock model on every scene. On, a later pass fills scenes marked dark when a least-censored model is installed.
- If you edit the prompt preview, that text replaces the compiled brief for the whole run.
