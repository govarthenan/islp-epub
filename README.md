# ISLP PDF to EPUB

Converts `ISLP_website.pdf` — *An Introduction to Statistical Learning with Applications in
Python*, 613 pages — into a reflowable EPUB 3 tuned for the Kobo Libra 2.

**For personal, educational and experimental use only. No commercial use.** All rights in the
text remain with the authors and the publisher. The source PDF is distributed free of charge
by the authors at statlearning.com; this repository only changes its format.

The finished book is `output/ISLP.epub`.

## What it does

| Part of the book | How it is carried over |
|---|---|
| Prose | Rebuilt paragraph by paragraph from the PDF's character stream; hyphenation undone from the book's own vocabulary |
| Inline mathematics | Sub- and superscripts recovered from the glyph geometry, so most of it stays reflowing HTML text |
| Accents, script letters | LaTeX generated from the character data, typeset to SVG by MathJax |
| Fractions, radicals, large operators, matrices | Cropped from the page, read by a vision model, checked against the page, typeset to SVG |
| Figures | Re-rendered from the vector art at 300 ppi, 16 levels of grey |
| Tables | Read back as real HTML so they reflow with the reader's font |
| Lab code | Jupyter input and output cells kept apart, alignment preserved |
| Cross-references | All 3,682 of the book's internal links resolved to EPUB anchors |
| Footnotes, margin notes, index | Kept, in forms that suit a 7 inch page |

`index.html` at the root tells the story of the conversion, including what failed and why.
`journal/JOURNAL.md` is the long-form engineering log.

## Choices made for the Kobo Libra 2

* No embedded font and no font size on `body`, so the reader's own typography controls work.
* Mathematics is SVG in `currentColor`, sized in `em`: it grows with the text and inverts
  correctly in dark mode.
* Figures at 300 ppi and 16 greys, matching the panel exactly.
* A `toc.ncx` beside the EPUB 3 navigation document, because Kobo still reads it.
* Code cells wrap rather than run off the edge, since an e-reader cannot scroll sideways.

## Running it

```bash
uv sync
npm install

uv run python src/extract_math_jobs.py    # crop every expression a model must read
# ... transcription and verification workflows write work/math_final.json ...
uv run python src/build_epub.py --out ISLP.epub
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/build_index.py          # regenerate the story page
```

Useful checks:

```bash
uv run python src/coverage_audit.py   # which page lines no block consumed
uv run python src/symbol_check.py     # symbols claimed vs symbols on the page
uv run python src/codex_audit.py 45   # independent second opinion, via OpenAI's codex CLI
```

`src/make_preview.sh output/ISLP.epub` unpacks the book and adds a browser-only stylesheet
that mimics the Libra 2's reading conditions, for checking pages at 1264 x 1680.

## Layout of the repository

```
src/islp/        the conversion library
  fonts.py       which font means prose, code or mathematics
  pagemodel.py   a page as visual lines, tagged by zone
  inline.py      characters to HTML, and the deterministic LaTeX generator
  blocks.py      lines to headings, paragraphs, equations, code cells, captions
  figures.py     finding and rendering figures, tables and mathematics regions
  document.py    pages to chapters
  epub.py        the EPUB 3 writer and the stylesheet
src/             pipeline entry points and checks
src/workflows/   multi-agent workflow scripts
work/            intermediate artefacts (not committed)
output/          the finished EPUB
```
