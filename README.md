# ISLP → EPUB

**A 613-page statistics textbook, rebuilt from its PDF into a reflowable EPUB 3 that a 7-inch e-reader can actually set.**

![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)
![EPUB](https://img.shields.io/badge/EPUB-3.0-85B735)
![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9)
![Status](https://img.shields.io/badge/status-complete-success)

A PDF is a picture of a page. It has one width, one font size, and no idea what a paragraph
is. On a 7-inch panel that is close to unreadable: you either squint at the whole page or you
pan around a zoomed fragment.

This project takes the PDF apart and puts the book back together as real text — paragraphs
that reflow, mathematics that scales with the font, tables that wrap, and 3,686 working
cross-references. The output is `output/ISLP.epub`, and it is committed to this repository.

## Start here

Two documents explain the problem and the answer. Read either one before the code.

| | What it gives you | Length |
|---|---|---|
| **[The conversion, explained →](docs/conversion-story.pdf)** | Why a PDF textbook fails on a small screen, and how each of the six stages fixes it. Pictures of the four cropping attempts, including the two that failed. **GitHub shows this PDF in the browser** — no download needed. | 10 pages |
| **[Engineering journal →](journal/JOURNAL.md)** | The same work in order, as it happened: 18 dated entries, with the dead ends and the corrections left in. | 498 lines |

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

---

## Quick start

```bash
uv sync          # Python dependencies
npm install      # MathJax, for typesetting the mathematics

uv run python src/build_epub.py --out ISLP.epub
uv run python src/validate_epub.py output/ISLP.epub
```

The full pipeline, from a fresh PDF:

```bash
uv run python src/probe_structure.py        # find the chapters, the index, the page zones
uv run python src/extract_math_jobs.py      # crop every expression a model must read
# transcription and verification write work/math_final.json
uv run python src/build_epub.py --out ISLP.epub
uv run python src/build_index.py            # regenerate the story page
./src/make_story_pdf.sh                     # and its PDF, for reading on GitHub
```

---

## What it does

| Part of the book | How it is carried over |
|---|---|
| Prose | Rebuilt paragraph by paragraph from the character stream; hyphenation undone against the book's own vocabulary |
| Inline mathematics | Sub- and superscripts recovered from glyph geometry, so most of it stays reflowing HTML text |
| Accents, script letters | LaTeX generated from the character data, typeset to SVG by MathJax |
| Fractions, radicals, matrices | Cropped from the page, read by a vision model, checked against the page, typeset to SVG |
| Figures | Re-rendered from the vector art at 300 ppi, 16 levels of grey |
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
| Mathematics kept as **text** | 5,974 of 6,690 occurrences (89%) |
| Mathematics as SVG | 716 |
| Mathematics as bitmap | **0** |
| Internal links resolved | 3,686 of 3,686 |
| EPUB size | 8.2 MB |

Every one of the 531 model-read expressions was checked a second time, independently,
against the printed page: **481 identical, 49 cosmetic differences, 1 wrong** — 99.8%
agreement. The single error was corrected. `work/math_verification.json` has the detail.

---

## Choices made for a 7-inch e-reader

* **No embedded font, no font size on `body`** — the reader's own typography controls stay in
  charge.
* **Mathematics is SVG in `currentColor`, sized in `em`** — it grows with the text and inverts
  correctly in dark mode. This is why nothing is a bitmap.
* **Figures at 300 ppi and 16 greys**, matching a grey-scale panel exactly.
* **A `toc.ncx` beside the EPUB 3 navigation document**, because Kobo still reads it.
* **Code cells wrap** rather than run off the edge, since an e-reader cannot scroll sideways.

Copy `output/ISLP.epub` to the Kobo's `KOBOeReader` volume; it is picked up on eject. Kobo
reads a plain EPUB directly. For Kobo's own extras — per-chapter page counts and in-text
dictionary look-up — convert it to `.kepub.epub` with Calibre and the KoboTouchExtended
driver. Nothing in the book depends on that.

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
docs/              the story page as a PDF, for reading on GitHub
journal/           the engineering log
assets/            illustrations for the story page
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

---

## Rights

**For personal, educational and experimental use only. No commercial use.**

All rights in the text, the figures and the mathematics of *An Introduction to Statistical
Learning* remain with the authors and with Springer Nature. The authors distribute the PDF
free of charge at [statlearning.com](https://www.statlearning.com/). This repository only
changes its format; it claims nothing over the content.

If you hold rights in the book and you want `output/ISLP.epub` taken down, open an issue and
it will be removed.

The conversion code in `src/` is the original work of the author of this repository. Note that
it depends on **PyMuPDF**, which is licensed AGPL-3.0 unless a commercial licence is bought;
plan accordingly if you reuse this code in your own project.

## Author

Govarthenan Rajadurai
