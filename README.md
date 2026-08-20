# ISLP → EPUB

**A 613-page statistics textbook, rebuilt from its PDF into a reflowable EPUB 3 that any e-reader can actually set.**

![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)
![EPUB](https://img.shields.io/badge/EPUB-3.0-85B735)
![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9)
![Code](https://img.shields.io/badge/code-MIT-blue)
![Docs](https://img.shields.io/badge/docs-CC%20BY%204.0-blue)
![Status](https://img.shields.io/badge/status-complete-success)

> ## ⚠ Read this first
>
> **Educational and experimental use only. No commercial use.**
>
> **The book is not mine.** This repository converts *An Introduction to Statistical Learning,
> with Applications in Python*. All rights in its text, figures, tables and mathematics stay
> with Gareth James, Daniela Witten, Trevor Hastie, Robert Tibshirani, Jonathan Taylor and
> Springer Nature. The authors give the PDF away free at
> [statlearning.com](https://www.statlearning.com/). This project changes the format only. It
> claims nothing over the content, and it grants no rights over the content. If you hold
> rights in the book and you want the EPUB files removed, open an issue and they will be
> removed.
>
> **Part of the mathematics was read by AI models.** 531 expressions were cropped from the
> page and transcribed by AI vision models. Every one was checked a second time, and a sample
> was audited by a different model family — 99.8% agreement, one error found and corrected.
> That measured the error rate. It did not remove it. **Check any equation before you rely on
> it for study, for an examination or for work.** The free PDF is the authority, not this
> conversion.
>
> **No warranty.** Nothing here is promised to be correct, and nothing is promised to open on
> your device.
>
> **[Full disclaimer →](DISCLAIMER.md)** · **[Rights in the book →](NOTICE)** ·
> **[Licence →](LICENSE)** · **[Contributing →](CONTRIBUTING.md)**

---

## Download the book

One build makes two books from one pass over the PDF. Both hold the same words, the same
figures and the same equations. They differ only in how the mathematics is drawn.

| Take this file | If you read with | Mathematics | Size |
|---|---|---|---|
| **[`output/ISLP.epub`](output/ISLP.epub)** | Kobo, Apple Books, Google Play Books, Thorium, KOReader, Calibre | SVG. Sharp at every font size, and the ink follows the reader's colour scheme. | 8.7 MB |
| **[`output/ISLP-raster.epub`](output/ISLP-raster.epub)** | **Moon+ Reader**, Send-to-Kindle, or anything that shows a box marked SVG | The same equations as PNG at 48 pixels for one em, drawn from the same SVG files. | 11.9 MB |

**If you do not know which one you want, take the first one.** If the equations appear as
small empty boxes, take the second one.

Moon+ Reader on Android draws no SVG at all, in an image, inline, or as a page. It shows a
small box with the label SVG where the equation should be. It has no MathML either. A raster
image is the only form it draws, which is why the second book exists.

**Kobo** — copy `output/ISLP.epub` to the `KOBOeReader` volume; it is picked up on eject.
Kobo reads a plain EPUB directly. For Kobo's own extras, per-chapter page counts and in-text
dictionary look-up, convert it to `.kepub.epub` with Calibre and the KoboTouchExtended
driver. Nothing in the book depends on that.

**Kindle** — send `output/ISLP-raster.epub` to your Send-to-Kindle address. Amazon's
converter does not always keep SVG, and it keeps a PNG.

**Moon+ Reader on Android** — use `output/ISLP-raster.epub`. In the night theme the
mathematics may come out black on a dark page, because Moon+ neither declares a dark colour
scheme to the page nor inverts the screen. Moon+ has a setting that inverts images at night.

**Apple Books, Google Play Books, Thorium, KOReader, Calibre** — open `output/ISLP.epub`
directly.

### The devices this was tested on

The book was built first for one **Kobo Libra 2**, a 7-inch e-ink reader, and every early
decision was measured against that one panel at 1264 × 1680.

That was not enough. A photograph came back from a **Samsung Galaxy S23 running Moon+
Reader**, opened at "Notation and Simple Matrix Algebra". Where a matrix should have been
there was a small empty box. That one photograph is the reason the second book exists, and it
is the reason `src/make_probe_epub.py` was written: it builds a one-page EPUB that shows the
same expression drawn eight different ways, so that a single photograph from any device
answers what that device can and cannot draw.

So "reads on any e-reader" means this: **measured on a Kobo Libra 2 and on a Galaxy S23 with
Moon+ Reader, and reasoned about for everything else.** Every other reader named above is
expected to work. None of them is confirmed to work.

**If your reader shows something wrong, send a photograph.** It is the most useful thing
anybody can give this project — see
[device report](https://github.com/govarthenan/islp-epub/issues/new?template=device-report.yml)
and [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

A PDF is a picture of a page. It has one width, one font size, and no idea what a paragraph
is. On a 7-inch panel that is close to unreadable: you either squint at the whole page or you
pan around a zoomed fragment.

This project takes the PDF apart and puts the book back together as real text — paragraphs
that reflow, mathematics that scales with the font, tables that wrap, and 3,686 working
cross-references.

## Start here

Two documents explain the problem and the answer. Read either one before the code.

| | What it gives you | Length |
|---|---|---|
| **[The conversion, explained →](docs/conversion-story.pdf)** | Why a PDF textbook fails on a small screen, and how each of the six stages fixes it. Pictures of the four cropping attempts, including the three that failed. **GitHub shows this PDF in the browser** — no download needed. | 12 pages |
| **[Engineering journal →](docs/JOURNAL.md)** | The same work in order, as it happened: 20 dated entries, with the dead ends and the corrections left in. The last two are the cross-device audit and the reader that draws no SVG. | 663 lines |

The PDF is rendered from [`index.html`](index.html), the interactive version of the same
story. Read it live at **[govarthenan.github.io/islp-epub](https://govarthenan.github.io/islp-epub/)**.
Opening `index.html` from the file list here shows raw markup, not the page.

---

## The source PDF is not in this repository

The book is *An Introduction to Statistical Learning, with Applications in Python* by Gareth
James, Daniela Witten, Trevor Hastie, Robert Tibshirani and Jonathan Taylor
(Springer, 2023). The authors give it away at **[statlearning.com](https://www.statlearning.com/)**.

To run the pipeline, download the PDF yourself and put it in the repository root as
`ISLP_website.pdf`. It is in `.gitignore` and it will never be committed.

Download it from the site, then:

```bash
mv ~/Downloads/ISLP_website.pdf .
```

### The copy this was converted

The pipeline was run against one printing of the PDF. Check that your download is the same
one:

```bash
sha256sum ISLP_website.pdf          # macOS: shasum -a 256 ISLP_website.pdf
```

| Property | Value |
|---|---|
| SHA-256 | `278d3bdd49a8a480c2ff8e03245822caad8a3a48e81afd6d039c52c8fc13ad60` |
| Size | 20,053,984 bytes |
| Pages | 613 |
| Made | 14 August 2023, Adobe InDesign 17.4 |

If the checksum agrees, the numbers in this README apply to your build. If it does not, you
have a different printing. The build still runs, but each expression is cropped by its page
and its position on that page, so run the full pipeline again from `src/probe_structure.py`
and do not carry over an old `work/math_final.json`. The counts in this README can move.

---

## Quick start

```bash
uv sync          # Python dependencies
npm install      # MathJax, for typesetting the mathematics

uv run python src/build_epub.py
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/validate_epub.py output/ISLP-raster.epub
```

Useful options on `src/build_epub.py`:

| Option | What it does |
|---|---|
| `--variants svg` | Write only `ISLP.epub`, and draw no PNG at all |
| `--variants raster` | Write only `ISLP-raster.epub` |
| `--pixels-per-em 32` | Draw the raster mathematics smaller. 48 is the default and costs 5.5 MB; 32 saves about 2 MB and stays sharp at a normal font, but not at a large one. The cache in `work/` names the size it was drawn at, so it throws itself away when this changes |
| `--limit 40` | Stop after 40 pages of the PDF. For a quick check of a change |

Check the drawing after any change to the raster path:

```bash
uv run python src/check_math_raster.py --sample 60 --contact-sheet
```

It confirms that every equation carries ink and that the glyph references are followed, and
it draws the 40 equations that stretch a bracket onto `work/math_stretchy_sheet.png`. Look at
that sheet with your own eyes: a stretched bracket is the thing a renderer gets wrong, and no
automatic test in this repository separates a broken one from ordinary differences between
renderers. See journal entry 020.

The full pipeline, from a fresh PDF:

```bash
uv run python src/probe_structure.py        # find the chapters, the index, the page zones
uv run python src/extract_math_jobs.py      # crop every expression a model must read
# transcription and verification write work/math_final.json
uv run python src/build_epub.py --out ISLP.epub
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/build_index.py            # regenerate the story page
./src/make_story_pdf.sh                     # and its PDF, for reading on GitHub
```

---

## What it does

| Part of the book | How it is carried over |
|---|---|
| Prose | Rebuilt paragraph by paragraph from the character stream; hyphenation undone against the book's own vocabulary |
| Inline mathematics | Sub- and superscripts recovered from glyph geometry, so most of it stays reflowing HTML text |
| Accents, script letters | LaTeX generated from the character data, typeset by MathJax |
| Fractions, radicals, matrices | Cropped from the page, read by an AI vision model, checked against the page, typeset by MathJax |
| Every typeset expression | SVG in one book, and the same file drawn as a PNG in the other |
| Figures | Re-rendered from the vector art at 300 ppi, in colour |
| Tables | Read back as real HTML, so they reflow with the reader's font |
| Lab code | Jupyter input and output cells kept apart, alignment preserved |
| Cross-references | Every internal link resolved to an EPUB anchor |
| Footnotes, margin notes, index | Kept, in forms that suit a small page |

## Results

| | |
|---|---|
| Chapters | 15 |
| Paragraphs | 3,297 |
| Code cells | 1,137 |
| Figures | 191, all re-rendered at 300 ppi |
| Tables | 36, all as reflowable markup — none as pictures |
| Display equations | 409 |
| Mathematics kept as **text** | 5,974 of 6,690 items (89%) |
| Mathematics typeset by MathJax | 716 expressions, 926 places |
| — of those, generated by rule, with no model | 185 |
| — of those, read from the page by an AI model | 531 |
| Mathematics left as a picture of the page | **0** |
| Internal links resolved | 3,686 of 3,686 |
| EPUB size | 8.7 MB with SVG, 11.9 MB with PNG |

Every one of the 531 model-read expressions was checked a second time, independently,
against the printed page: **481 identical, 49 cosmetic differences, 1 wrong** — 99.8%
agreement. The single error was corrected. A sample was then audited by a different model
family, through OpenAI's `codex` command line tool: 44 of 45 agreed, and **the one
disagreement was real and mattered** — no check inside the pipeline had caught it. Three
faults in the extraction were fixed because of it, and a repeat audit of 50 found no
disagreement. `work/math_verification.json` has the detail, and journal entry 014 has the
argument.

**None of that makes the mathematics certain.** See [`DISCLAIMER.md`](DISCLAIMER.md).

---

## Choices made for the reader, not for one device

Every decision below holds on a 6-inch Kindle, a colour Kobo, a phone, a tablet or a desktop
window, and not only on the panel it was first measured against.

* **No embedded font, no font size on `body`** — the reader's own typography controls stay in
  charge. Every length in the stylesheet is relative.
* **Mathematics is sized in `em` in both books**, so it grows with the text. This is why
  nothing is cropped from the page. In the SVG book each file carries two rules of its own
  that follow a dark theme, because an `<img>` is a separate document and `currentColor`
  alone cannot reach it from the page. A PNG can carry no rules, so the raster book turns its
  mathematics over with `filter: invert(1)` in the page stylesheet instead. Figures are left
  out of that rule: a photograph must not be inverted.
* **No colour is set without its partner, and there is a dark-scheme block.** A reader that
  repaints the page with its own colours cannot leave dark text on a light block.
* **Figures at 300 ppi, in colour.** The book draws one series in orange and the next in
  blue, and the two have almost the same luminance, 84 and 82 of 255. Rendered in grey they
  came out the same shade and the series could not be told apart. A grey e-ink screen
  converts the colour itself, so it loses nothing.
* **Hyphenation asked for in four spellings**, because a justified narrow column without it
  opens rivers of white space on Adobe-based readers.
* **A `toc.ncx` beside the EPUB 3 navigation document**, because Kobo and older Adobe-based
  readers still use it.
* **Code cells wrap** rather than run off the edge, since an e-reader cannot scroll sideways.
* **An "About this conversion" page after the cover**, in both books, because the rights
  statement and the caution about the mathematics must travel with the file. A README stays
  on GitHub; the file goes to the device.

---

## Repository layout

```
src/islp/          the conversion library
  fonts.py         which font means prose, code or mathematics
  pagemodel.py     a page as visual lines, tagged by zone
  inline.py        characters to HTML, and the deterministic LaTeX generator
  blocks.py        lines to headings, paragraphs, equations, code cells, captions
  figures.py       finding and rendering figures, tables and mathematics regions
  document.py      pages to chapters
  epub.py          the EPUB 3 writer and the stylesheet
  symbols.py       the symbol inventory used by the checks
src/               pipeline entry points and checks
src/workflows/     multi-agent verification workflow scripts
work/              intermediate artefacts, and the audit records
output/            the finished EPUB
docs/              the story as a PDF, the engineering log, and the data behind both
assets/            illustrations for the story page
.github/           issue forms for device reports and equation errors

DISCLAIMER.md      the full statement: purpose, rights, the AI mathematics, no warranty
NOTICE             the rights in the book, and the takedown offer
LICENSE            MIT, for the pipeline in src/
LICENSE-DOCS       CC BY 4.0, for the writing
CONTRIBUTING.md    what this project needs, and how to run it
```

## Checks

```bash
uv run python src/coverage_audit.py      # which page lines no block consumed
uv run python src/symbol_check.py        # symbols claimed vs symbols on the page
uv run python src/validate_epub.py output/ISLP.epub
uv run ruff check src/ && uv run ruff format --check src/
```

`src/make_preview.sh output/ISLP.epub` unpacks the book and adds a browser-only stylesheet
that mimics the panel's reading conditions, for checking pages at 1264 × 1680.

```bash
uv run python src/check_math_raster.py --sample 60 --contact-sheet
```

checks the raster mathematics, and `src/make_probe_epub.py --out <path>` writes a one-page
EPUB that shows the same expression drawn eight ways. Open that on a device and one
photograph tells you what the device can and cannot draw. It is how the Moon+ Reader
questions in journal entry 020 were settled.

---

## Known, and not yet done

* **Moon+ Reader's night theme is unchecked.** It neither declares a dark colour scheme to the
  page nor inverts the screen, so the `filter: invert(1)` that serves Thorium, Apple Books and
  Calibre may not reach it, and the mathematics may read black on a dark page. Moon+ has a
  setting that inverts images at night. Dark mode on the Kobo Libra 2 is unchecked too.
* **547 of the 926 places that use an image do not need one.** 349 of the 716 expressions hold
  no two-dimensional structure at all — `\hat{f}`, `A ∈ ℝ^{r×s}` — and 411 of those places are
  inline, inside a sentence. They are images only because one condition in
  `src/islp/inline.py` sends a run with an accent or a script letter down the image path.
  Unicode can show both: `x̂` is `x` with U+0302, `ℝ` is U+211D. Moving them would give real
  reflowing text in **both** books and shrink the raster one. The risks — an accent sitting off
  centre, a rare script letter with no glyph in a device font — need measuring on a device
  first, with the probe above.
* **48 pixels for one em has not been tested at a large reading font on a real device.** It is
  the safer choice until it is; `--pixels-per-em 32` would save about 2 MB.

Journal entry 020 has the measurements behind all three. Each one needs a person with a
device rather than a person with a keyboard — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Contributing

Issues and pull requests are welcome, and so is redistribution of the books within the limits
in [`NOTICE`](NOTICE).

**The single most useful thing you can send is a photograph of a page that is wrong on your
device.** The conversion was measured on two devices; everything else is reasoned about. No
test in this repository can produce that evidence, and the second book exists only because
one photograph arrived.

* [Report a device fault](https://github.com/govarthenan/islp-epub/issues/new?template=device-report.yml)
* [Report an equation that does not match the book](https://github.com/govarthenan/islp-epub/issues/new?template=math-error.yml)
* [`CONTRIBUTING.md`](CONTRIBUTING.md) — the three open questions, how to run the pipeline, and
  the house rules

---

## Licence and rights

**For personal, educational and experimental use only. No commercial use.**

| What | Terms | |
|---|---|---|
| The conversion pipeline in `src/` | MIT | [`LICENSE`](LICENSE) |
| The writing: `README.md`, `docs/`, `index.html`, `assets/` | CC BY 4.0 | [`LICENSE-DOCS`](LICENSE-DOCS) |
| The book, and the two EPUB files derived from it | **Not licensed.** All rights reserved by the authors and Springer Nature. | [`NOTICE`](NOTICE) |

All rights in the text, the figures and the mathematics of *An Introduction to Statistical
Learning* remain with the authors and with Springer Nature. The authors distribute the PDF
free of charge at [statlearning.com](https://www.statlearning.com/). This repository only
changes its format; it claims nothing over the content.

If you hold rights in the book and you want `output/ISLP.epub` and `output/ISLP-raster.epub`
taken down, open an issue or write to <dev@dreamspace.tech>, and they will be removed.

**If you reuse the code:** it depends on **PyMuPDF**, which is licensed AGPL-3.0 unless a
commercial licence is bought. MIT on this source is compatible with that, but a combined work
you distribute is subject to the AGPL. [`LICENSE`](LICENSE) explains it.

The full statement, including the caution about the machine-read mathematics, is in
[`DISCLAIMER.md`](DISCLAIMER.md).

## Author

The conversion is the work of **Govarthenan Rajadurai**.
The book is the work of its authors, and stays theirs.
