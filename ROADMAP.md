# Roadmap

This is the public plan for VOXPrint AI Plotweaver. It has no dates. The release you can install now is 0.2.0 RC.

## Next version (near-term)

The window will let you edit the story bible and the outline before the draft continues. Today the app writes those files and can wait while you read them on disk. The next version opens them in the window so you can change them first.

Reference books will get a style reading. The app already accepts `.txt`, `.md`, `.docx`, and `.epub`, uses them for structure, and checks that the draft does not copy them. Next it will write down the style it found and use that description while it drafts.

Sound markup will be easier to review and change. It will still go into a second file, `book.sound.vxbook`. The original `book.vxbook` stays as it was.

The command line will cover the same actions as the window, including the choices that today exist only as buttons.

Real-world grounding is optional and off by default. Plotweaver stays fully usable offline. When you turn it on, Help me write the brief also reads your notes for real-world topics. Notes about spaceflight can bring in real launches. A present-day setting can bring in current events, places, prices, and weather. The app searches news and reference sites and keeps the key facts. Those facts go into the story bible as a Real-world context section, each with a source link and the date it was retrieved. Every chapter can draw on that list, including a future-set book that looks back on history, so the draft can use the facts where the local model has a gap. You review the list and can strike any item before writing starts. An optional filter drops political topics.

The same switch covers a historical setting. Everyday-life fiction set in a past decade, with characters facing hardship and persecution, can gather period detail: daily life, prices, rationing, laws, and documented real events and places. Those details come from reference and archive sources, so the plot can be woven around real moments. You can add footnotes or a short Historical notes appendix to the book, with the sources named. The facts stay in the story bible with their source links. Real living people are never used as characters.

## Later

Large writing models should run well on a 16 GB card. Memory will be placed on purpose. Mixture-of-experts layers that do not fit on the card move to RAM and run on the CPU. The KV cache for a long context can live in RAM. Weights the card will need next are fetched ahead of the step that uses them.

Audiobook Builder will take the finished book through `.vxbook`. The text, the speakers, and the sound cues travel in that file. When sound markup is on, import `book.sound.vxbook`.

## Models

The app picks a model tier from the card. Under 24 GB it uses the 16 GB tier and keeps 2 GB free. At 24 GB or more it uses the 24 GB tier and keeps 3 GB free. Settings can choose the other tier when the card can run it.

The stock download is the lineup for that tier. A 16 GB card gets Gemma 4 12B and T-lite-it-2.1 in Q4_K_M and Q5_K_M. A 24 GB card also gets T-pro-it-2.1. A file Audiobook Builder has already stored in the shared model folder is reused.

Least-censored models are a separate download from Settings. On a 24 GB card the published files are the abliterated Qwen 27B and Gemma 31B quants. On a 16 GB card they are smaller quants of those models, plus a Russian T-lite file when that file is published. The stock install leaves them out until you ask.

The memory placement described under Later is how a 16 GB card will run larger writing models. The tier split stays.

## Features

- A novel from a synopsis, on your machine, with local models only.
- A 16 GB tier and a 24 GB tier, with an optional least-censored download for each.
- A story bible and an outline you can read and edit.
- Style taken from reference books you choose, without copying those books into the novel.
- EPUB 3, FictionBook 2.1, DOCX, Markdown, and a Voxprint Book (`.vxbook`).
- Sound markup in a second `.vxbook`.
- A hand-off to Audiobook Builder through that `.vxbook`.
- The same actions in the window and on the command line.
