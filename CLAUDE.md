# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A one-way conversion pipeline. It takes one input, the ISLP textbook PDF, and writes two
EPUB 3 files. It is not a library and it is not a service. Almost every script is an entry
point that reads one or more JSON files from `work/` and writes another one back.

## Before anything runs

The source PDF is not in git. Put your own copy in the repository root as
`ISLP_website.pdf` (download it from statlearning.com). **Never commit it.** The pipeline was
measured against one printing; confirm yours with
`sha256sum ISLP_website.pdf` against `278d3bdd49a8a480c2ff8e03245822caad8a3a48e81afd6d039c52c8fc13ad60`.
A different printing moves every crop, so the counts in `README.md` no longer apply and
`work/math_final.json` must not be carried over.

```bash
uv sync          # Python 3.14, PyMuPDF, CairoSVG, Pillow, ruff
npm install      # mathjax-full, used by src/render_math.cjs
```

Run every script from the repository root. Several scripts open `ISLP_website.pdf` by a
relative path, and the entry points in `src/` reach the library with
`sys.path.insert(0, Path(__file__).parent)`, so `uv run python src/<name>.py` is the only
supported form.

## Commands

```bash
# Build. One pass over the PDF writes both books.
uv run python src/build_epub.py
uv run python src/build_epub.py --limit 40           # first 40 pages; use this while working
uv run python src/build_epub.py --variants svg       # skip the raster book and all PNG drawing
uv run python src/build_epub.py --pixels-per-em 32   # smaller raster mathematics

# Checks. There is no pytest suite; these audit scripts are the tests.
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/validate_epub.py output/ISLP-raster.epub
uv run python src/coverage_audit.py                  # page lines that no block consumed
uv run python src/symbol_check.py                    # symbols claimed vs symbols on the page
uv run python src/check_math_raster.py --sample 60 --contact-sheet

# Lint and format. Required before every commit.
uv run ruff check src/ && uv run ruff format --check src/

# The story page and its PDF. Always regenerate the two together.
uv run python src/build_index.py
./src/make_story_pdf.sh

# Look at pages in a browser under Kobo Libra 2 conditions (1264 x 1680).
src/make_preview.sh output/ISLP.epub
```

`src/check_math_raster.py` compares a renderer against itself. It cannot tell a broken
stretched bracket from an ordinary difference between renderers, so a person must look at
`work/math_stretchy_sheet.png` after any change to the raster path.

## Architecture

### Two layers

`src/islp/` is the library. It holds all knowledge of the book's geometry and typography.
`src/*.py` are entry points: probes, extractors, checks and the build. Entry points do
input and output; the library does the conversion.

The library is a pipeline of transforms, each one taking the output of the one before:

```
fonts.py      font name -> prose, code or mathematics (the two font families never overlap)
pagemodel.py  PDF page  -> visual lines, each tagged with a zone, by measured coordinates
inline.py     characters -> HTML, plus the TEXT / LATEX / VLM tier decision
blocks.py     lines     -> headings, paragraphs, equations, code cells, captions, list items
figures.py    regions above captions -> 300 ppi colour PNG for figures and tables
document.py   pages     -> chapters, paragraphs stitched over page breaks, hyphens undone
epub.py       document  -> EPUB 3 package and stylesheet
mathraster.py MathJax SVG -> transparent PNG, drawn by CairoSVG
```

### The tier decision drives everything

`inline.py` grades each run of mathematics into one of three tiers, and that grade decides
how much work the rest of the pipeline does:

* **TEXT** — plain HTML with `<i>`, `<sub>`, `<sup>` and Unicode. 89% of items. Free.
* **LATEX** — LaTeX generated here from the character data, typeset later by MathJax.
* **VLM** — the structure is not in the character stream at all (a fraction bar, a radical,
  a large operator), so the expression must be cropped and read by a vision model.

### The mathematics pipeline needs models in the loop

This is the part that cannot be run end to end by one command. The order is:

```
src/extract_math_jobs.py     crops + work/math_jobs_vlm.json
src/reuse_transcription.py   match new crops to old ones by image digest;
                             writes work/math_batches/ holding only what is unread
  -> agents read each batch, run src/check_latex.py on their own output,
     and write work/math_transcription_parts/
src/merge_transcription.py   -> work/math_transcription.json (+ work/math_missing.json)
src/render_candidates.py     typeset each candidate, stack it under the original crop
                             -> work/math_compare/<id>.png
src/symbol_check.py          free deterministic cross-check, no model
  -> src/workflows/verify_math.js (a Workflow script) fans out one refuting agent per
     batch over the comparison images -> work/math_verdicts/
src/codex_audit.py           independent audit through a different model family
src/apply_verdicts.py        -> work/math_final.json, work/math_verification.json
```

`build_epub.py` reads `work/math_final.json` when it exists and falls back to
`work/math_transcription.json`. Tables follow the same shape:
`extract_table_jobs.py` -> agents -> `merge_tables.py` -> `work/tables_html.json`.

### One build, two books

`build_epub.py` makes one pass over the PDF and writes both variants. The SVG files in
`work/math_svg/` are the single source of truth: the raster book draws its PNG from those
same SVG files, never from the PDF, so the two books can never disagree about what an
equation says. `work/math_png_cache.json` keys on the pixels-per-em and the renderer name,
so it throws itself away when either changes.

CairoSVG draws the PNG, not MuPDF. MuPDF misplaces the nested `<svg>` viewport that MathJax
uses to stretch a tall bracket, so every bracket around a matrix came out broken.
`svg_to_png_mupdf` stays only so the two renderers can be compared in `check_math_raster.py`.

### Colour and the reader's control

`epub.py` and `render_math.cjs` both carry rules that exist for a reason recorded in the
journal. Do not simplify them away:

* No embedded font and no font size on `body`. Every length is relative.
* Mathematics is sized in `em`, in both books, so it grows with the reader's font.
* Each SVG file carries its own two-rule stylesheet, because an `<img>` is a separate
  document and `currentColor` cannot reach it from the page.
* A PNG can carry no rules, so the raster book turns its mathematics over with
  `filter: invert(1)` in the page stylesheet — on the mathematics only, never on a figure.
* Every colour is declared as a foreground and background pair, and every pair has a
  dark-scheme counterpart.
* A `toc.ncx` is written beside the EPUB 3 navigation document, for Kobo and older Adobe
  readers.

## Generated files: do not edit by hand

| File | Written by |
|---|---|
| `index.html` | `src/build_index.py`, from `docs/attempts.json`, `work/build_stats.json` and `work/math_verification.json` |
| `docs/conversion-story.pdf` | `./src/make_story_pdf.sh`, from `index.html` |
| `output/*.epub` | `src/build_epub.py` |
| `work/*` | the pipeline |

Edit `docs/attempts.json` or `src/build_index.py`, then rebuild both the page and its PDF.
The numbers on the page come from the build files on purpose, so the page cannot drift from
the build. `src/make_probe_epub.py` must be given `--out` outside `output/`.

## House rules from CONTRIBUTING.md

* **Measure, do not guess.** Every threshold in this pipeline came from a measurement of the
  PDF. If you add one, say in a comment where the number came from. The existing comments
  name page coordinates, font sizes and colours; keep that style.
* **Write down what failed.** `docs/JOURNAL.md` keeps 20 dated entries with the dead ends
  left in. Add an entry when an attempt fails, not only when one succeeds.
* **Never remove a rights statement**, a takedown offer or the AI disclaimer from
  `README.md`, `index.html`, `NOTICE`, `DISCLAIMER.md`, or the "About this conversion" page
  inside either book. That page is `ABOUT_PAGE` in `src/build_epub.py`, and it goes into
  both variants.
* **Never "correct" an equation without evidence** from the printed page.
* Ruff settles style: 120 columns, `E501` and `SIM108` off (a comment above an if/else is
  the point, so it must not become a one-liner).

## Licences in one repository

`src/` is MIT (`LICENSE`). The writing — `README.md`, `docs/`, `index.html`, `assets/` — is
CC BY 4.0 (`LICENSE-DOCS`). The book and both EPUB files are not licensed; all rights stay
with the authors and Springer Nature (`NOTICE`). PyMuPDF is AGPL-3.0, which reaches any
combined work that is distributed.
