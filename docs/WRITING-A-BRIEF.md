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

Leave `chapters` and `scenes_per_chapter` empty to derive them. At 250 words per page, 40 pages is 10,000 words. The automatic chapter count for that length is 8, and a short English book keeps 2 scenes per chapter. A longer book, and a Russian book, adds scenes so each one fits a single draft. Type a chapter count when you want a different split. The longest length this pipeline treats as reliable is 2,000 pages.

## A good brief and a weak one

A good brief names the people, the place, the turn, and the ending, and it says the point of view and the tense. The synopsis agrees with those fields.

A weak brief is only a mood ("something sad in space") or a synopsis that implies a different narrator than the point-of-view field. The generator is told to keep the fields, so a mismatch shows up as a book that ignores the synopsis or a synopsis that ignores the fields. Make them agree before you start.

## Length

Words are pages times words per page. The form shows both numbers and the resulting word count. These planning labels are estimates, not measured run times. A longer book is more chapters, and each chapter is its own set of local model calls.

| Pages | Words at 250 per page | Chapters if left at 0 | Planning label |
| --- | --- | --- | --- |
| 40 | 10,000 | 8 | short, one sitting |
| 80 | 20,000 | 8 | short |
| 160 | 40,000 | 13 | medium, several hours |
| 320 | 80,000 | 25 | long, many hours |

The 16 GB tier uses the smaller stock model and keeps 2 GB free. The 24 GB tier uses the larger stock model and keeps 3 GB free. The larger model does more work per call, so a 24 GB card is not a shortcut to a shorter wait for the same page count. A long run can pause while the card is hot and resume when it cools.

## Tips

- Check every **Guessed** mark before you start. Those values were filled in because the notes were silent.
- Point of view and tense are binding. "Third-person limited" and "past" are the defaults when a draft has to choose.
- One character needs a name. Role, a short description, and gender (`male`, `female`, or `unspecified`) go with it.
- Plot points are one per line. They are the turns you want kept, not a scene list.
- Dark themes off keeps the stock model on every scene. On, a later pass fills scenes marked dark when a least-censored model is installed.
- If you edit the prompt preview, that text replaces the compiled brief for the whole run.
