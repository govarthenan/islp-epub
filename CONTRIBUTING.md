# Contributing

Thank you for looking at this. Contributions are welcome, and so is redistribution of the
books, within the limits in [`NOTICE`](NOTICE).

Read [`DISCLAIMER.md`](DISCLAIMER.md) first. It says what this project is, whose rights the
book is under, and why the mathematics needs to be checked.

---

## What this project needs most: a photograph from your device

The conversion was measured on **two** devices: a Kobo Libra 2 and a Samsung Galaxy S23
running Moon+ Reader. Everything else — Apple Books, Google Play Books, Thorium, KOReader,
Calibre, Kindle — is expected to work. It is not confirmed to work.

The single most useful thing you can send is a photograph of a page that is wrong.

That is not a small contribution. The second book in this repository exists because one
photograph came back from a Galaxy S23 showing an empty box where a matrix should have been.
No test in this repository could have found that. Only a device could.

**[Open a device report →](https://github.com/govarthenan/islp-epub/issues/new?template=device-report.yml)**

If you want to help but you have no fault to report, `src/make_probe_epub.py` writes a
one-page EPUB that shows the same expression drawn eight different ways. Open it on your
device, photograph the page, and post it. One photograph tells this project what your device
can and cannot draw.

```bash
uv run python src/make_probe_epub.py --out /tmp/probe.epub
```

---

## The three open questions

Each of these needs a person with a device, not a person with a keyboard. The measurements
behind all three are in journal entry 020.

**1. Moon+ Reader's night theme.** Moon+ neither declares a dark colour scheme to the page nor
inverts the screen, so the `filter: invert(1)` rule that serves Thorium, Apple Books and
Calibre may never reach it. The mathematics may read black on a dark page. Moon+ has a setting
that inverts images at night, which may be the answer. **What is needed:** open
`output/ISLP-raster.epub` in Moon+ Reader, turn on the night theme, and photograph a page that
has an equation on it.

**2. Dark mode on the Kobo Libra 2.** Unchecked since the book was built. **What is needed:**
open `output/ISLP.epub` on a Kobo, turn on dark mode, and photograph a page with an equation.

**3. The size of the raster mathematics.** The PNG mathematics is drawn at 48 pixels for one
em. That costs 5.5 MB. `--pixels-per-em 32` would save about 2 MB and it stays sharp at a
normal reading font — but nobody has looked at it on a real device at a large reading font.
**What is needed:** build with `--pixels-per-em 32`, read it at your largest comfortable font,
and say whether the equations look soft.

```bash
uv run python src/build_epub.py --variants raster --pixels-per-em 32
```

---

## An equation that is wrong

531 expressions were read off the page by AI vision models. The error rate was measured, not
removed. See [§3 of the disclaimer](DISCLAIMER.md#3-the-mathematics-was-read-by-ai-models).

If you find an equation that does not match the book,
**[open an equation error report](https://github.com/govarthenan/islp-epub/issues/new?template=math-error.yml)**.
A photograph of the printed page beside the screen is enough. You do not need to know LaTeX,
and you do not need to propose a fix.

Please check the free PDF at [statlearning.com](https://www.statlearning.com/) first, so that
a difference in the book is not reported as a fault in the conversion.

---

## Working on the code

### Set up

```bash
uv sync          # Python dependencies
npm install      # MathJax, for typesetting the mathematics
```

You must supply your own copy of the source PDF. Download it from
[statlearning.com](https://www.statlearning.com/) and put it in the repository root as
`ISLP_website.pdf`. **Never commit it.** It is in `.gitignore` and a pull request that adds it
will be refused.

The build commands are in the [README](README.md#quick-start). Use `--limit 40` while you work,
so a change can be checked in seconds instead of minutes.

```bash
uv run python src/build_epub.py --limit 40
```

### Before you open a pull request

```bash
uv run ruff check src/ && uv run ruff format --check src/
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/validate_epub.py output/ISLP-raster.epub
```

If you touched the raster path, look at the contact sheet with your own eyes. A stretched
bracket is the thing a renderer gets wrong, and no automatic test in this repository separates
a broken one from an ordinary difference between renderers:

```bash
uv run python src/check_math_raster.py --sample 60 --contact-sheet
```

If you touched the story page, regenerate the page and its PDF together, so the two cannot
drift apart:

```bash
uv run python src/build_index.py
./src/make_story_pdf.sh
```

### House rules

* **Python style:** type hints on every parameter and return, `snake_case`, 120 columns.
  `ruff` settles the rest.
* **Measure, do not guess.** Every rule in this pipeline was measured from the PDF before it
  was written down. If you add a threshold, say in a comment where the number came from.
* **Write down what failed.** `docs/JOURNAL.md` keeps the dead ends. A dead end that is
  recorded stops the next person from walking into it.

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <description>`.
Write the description in the present tense, and say what the change does for the reader rather
than which function it edits. From this repository's own history:

```
fix(epub): make the book read correctly on readers other than a Kobo
feat(lists): three levels of exercise item, keyed on the marker
docs(journal): record what the independent audit caught
```

---

## Redistributing the books

You may copy and pass on `output/ISLP.epub` and `output/ISLP-raster.epub` for personal and
educational use. If you do:

* keep the **"About this conversion"** page that is inside the file;
* keep [`NOTICE`](NOTICE) with it;
* **do not sell it**, and do not charge for access to it.

The book is not mine to license. See [`NOTICE`](NOTICE) for the full statement.

---

## What will not be accepted

* **The source PDF committed to the repository.** Ever.
* **Any change that removes a rights statement, a takedown offer or the AI disclaimer** from
  the README, the story page, `NOTICE`, `DISCLAIMER.md` or the "About this conversion" page
  inside either book.
* **An equation "corrected" without evidence.** Send the photograph of the printed page. A
  correction from memory cannot be checked, and this project has already learned that a
  confident answer and a correct answer are not the same thing.

---

## Licences

| What you are changing | Terms |
|---|---|
| Code in `src/` | [MIT](LICENSE) |
| Writing in `README.md`, `docs/`, `index.html`, `assets/` | [CC BY 4.0](LICENSE-DOCS) |
| The book, and the two EPUB files | Not licensed. See [`NOTICE`](NOTICE). |

By opening a pull request you agree that your contribution is supplied under the licence that
covers the file you changed.
