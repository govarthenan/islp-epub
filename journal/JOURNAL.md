# ISLP PDF to EPUB — Engineering Journal

Purpose: convert `ISLP_website.pdf` (613 pages, *An Introduction to Statistical Learning with
Applications in Python*) into a reflowable EPUB that reads well on a Kobo Libra 2 (7 inch,
1264 x 1680 px e-ink).

Scope: educational and experimental only. No commercial use.

Each entry records what was tried, what happened, and what was decided.

---

## 2026-08-17 — Entry 001: Environment survey

**Attempt.** Find which PDF and EPUB tools are on the machine.

**Result.** Available: poppler-utils (pdftotext, pdfimages, pdftoppm, pdfinfo, pdffonts), qpdf,
ghostscript 10.02.1, python 3.12 + uv, node 24, codex-cli 0.147.0.
Missing: pandoc, calibre/ebook-convert, mutool, java, tesseract.

**Decision.** Build the EPUB directly in Python. An EPUB is a ZIP with XHTML, so a hand-built
writer gives full control of the markup, which matters more here than the convenience of a
converter. `epubcheck` needs java, so structural validation must be written in Python too.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 002: PDF structure probe

**Attempt.** `src/probe_structure.py` — read the outline, count fonts, sizes, images.

**Result.**
- 613 pages, page box 504.567 x 720 pt.
- 309 outline (bookmark) entries with correct titles and page numbers, 3 levels deep.
- Body text: `LMRoman10-Regular` (Latin Modern). Code: `LMMono8-Regular` / `LMMono9-Regular`.
- Mathematics: `CMMI*`, `CMSY*`, `CMEX*`, `CMR*`, `MSBM*` (Computer Modern).
- Only 44 embedded raster images on 24 pages.

**Two findings that shape the whole design.**
1. Prose fonts (LM*) and math fonts (CM*/MSBM*) are disjoint families. Mathematics can
   therefore be located exactly, by font name, with no OCR and no guessing.
2. Nearly every figure is vector art, not a raster image. Figures cannot be pulled out with
   `pdfimages`; they must be rendered from page regions.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 003: Mathematics census

**Attempt.** `src/probe_math.py` — count math lines and measure how long the inline math runs are.

**Result.**
- 8,213 text lines contain math glyphs; 30,178 math glyphs in total.
- ~846 lines look like display equations (centred, mostly math).
- 9,362 inline math runs. 61% of them are 3 glyphs or shorter (`n`, `p`, `X1`, `β0`, `f`).

**Extraction quality.** Unicode comes out well: `β`, `ϵ`, `×`, `≈`, `∈`, `−` are all correct.
What is lost is **structure**, not characters: `x_{ij}` extracts as `xij`, `\hat{Y}` as `ˆY`,
`\sum_{k=1}^{d}` as `)d k=1`, and multi-line equations break into unrelated lines.

**Decision (hybrid math strategy).** Confirms Gova's friend's diagnosis, but only for part of
the problem:
- **Simple inline math** (a variable, with or without a sub/superscript) is rebuilt
  deterministically from character data. Font size drop plus baseline shift identifies
  sub/superscripts exactly (measured: `x` at size 10 origin y=368.0, then `ij` at size 7
  origin y=369.5). This gives reflowable HTML text, which is far better on e-ink than
  thousands of tiny images, and it costs no model calls.
- **Display equations and complex inline math** (fractions, hats, big operators, matrices) are
  cropped to images, sent to a vision model for LaTeX, then verified adversarially.

**Status.** SUCCESS (measurement). Strategy set.

---

## 2026-08-17 — Entry 004: Layout probe

**Attempt.** `src/probe_layout.py` — histogram of line boxes, plus character-level dumps.

**Result.**
- Main text column: x from 91.0 to 413.8.
- Margin notes: x from ~419 to ~470, in `LMRoman8-Regular` at size 8. **They are interleaved
  into the main text lines** by the extractor, so "...the squared" comes out as
  "...the squared expected". They must be split out by x position or they corrupt the prose.
- Running heads sit at y 32.9-45.7 and must be dropped.
- Headings: `LMRoman12-Italic` size 12 for subsections; size 14.3 for chapter titles.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 005: Colour carries meaning

**Attempt.** Work out how to tell lab code, Jupyter prompts, lab sub-headings and margin
notes apart, since all four sit outside the ordinary paragraph flow.

**Result.** Span colour separates them exactly:

| colour  | meaning                                            |
|---------|----------------------------------------------------|
| #000000 | prose                                              |
| #984100 | code inside a lab cell                             |
| #0068b4 | `In [n]:` / `Out[n]:` prompts, lab sub-headings, cross-reference links |
| #595959 | margin note                                        |

Code cells are also backed by filled rectangles: cream `(1.00, 0.96, 0.90)` for input and
white `(1, 1, 1)` for output. That gives the input/output split for free.

**Status.** SUCCESS. This removed all guesswork from lab pages.

---

## 2026-08-17 — Entry 006: First end-to-end EPUB

**Attempt.** Build the whole chain — page model, block assembly, figure rendering, MathJax
SVG, EPUB 3 packaging — and run it over the first 100 pages.

**Result.** A 1.6 MB EPUB that passes the structural checks written in
`src/validate_epub.py` (`epubcheck` needs Java, which is not installed).

**Faults found by looking at the rendered pages in a browser at 1264 x 1680, the Kobo Libra 2
panel size**, and what each turned out to be:

1. *"2.1.2How Do We Estimate f?"* — the extractor emits no space where two spans merely sit
   apart on the page. **Fix:** insert a space wherever the horizontal gap exceeds
   `max(1.2 pt, 0.2 x font size)`.
2. *"f it a model with 11 variables"* in a code cell — ligature expansion gave `f` and `i`
   the same pen position, and the column arithmetic then invented a space. **Fix:** keep
   ligatures as single glyphs during extraction and expand them when writing text out.
3. *Figure captions split in two* — the first prose line of a page was being treated as a new
   paragraph. **Fix:** rely only on the 9.9 pt first-line indent.
4. *Ten margin notes stacked in a column* — faithful to the printed margin, unreadable on a
   7 inch page. **Fix:** collapse the notes belonging to one paragraph onto a single quiet
   line separated by middots.
5. *"concatenat-" and "ion" as two separate notes* — margin note lines are 14.9 pt apart, and
   after sorting by baseline they are not adjacent in the line list. **Fix:** group margin
   lines by vertical proximity across the whole page, then de-hyphenate.
6. *Paragraph indents driven by CSS sibling rules disagreed with the book.* **Fix:** record
   whether each paragraph was indented on the printed page and set the class from that.

**Status.** SUCCESS after six fixes.

---

## 2026-08-17 — Entry 007: What the deterministic LaTeX generator covers

**Attempt.** Measure how much mathematics can be reconstructed with no model at all.

**Result.** Over the whole book the math runs split three ways:

- **TEXT** — plain HTML with `<i>`, `<sub>`, `<sup>` and Unicode. The large majority.
- **LATEX** — LaTeX generated from the character data, then rendered to SVG by MathJax.
  Triggered by accents and by script letters. 497 occurrences, 280 distinct.
  Examples produced: `\hat{Y} = \hat{f}(X)`, `\mathbf{A} \in \mathbb{R}^{r\times s}`.
- **VLM** — a vision model is needed. 894 occurrences, 482 distinct. Triggered by a CMEX
  glyph (a large operator or delimiter), a fraction or radical rule, or a wide accent.

So the friend's diagnosis was right, but only for the third group. Roughly two thirds of the
"hard" mathematics turned out to be recoverable exactly, for free, from the PDF's own
character stream.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 008: Cropping mathematics correctly (the hardest part so far)

**Attempt.** Cut each expression that needs a vision model out of the page as an image.

**What went wrong, in four rounds.**

*Round 1 — boxes too small.* A math run's box came from one text line, but a fraction puts
its numerator, its rule and its denominator on three different baselines, which the extractor
files as three separate lines. Crops showed the middle of a fraction with the top and bottom
sliced off. **FAILED.**

*Round 2 — boxes too greedy.* Growing the box to include neighbouring mathematics glyphs
pulled in the equation number `(3.4)` from the following paragraph line, because `(3.4)` is
set in a Computer Modern font and so counts as mathematics. One crop contained two lines of
prose. **FAILED.**

*Round 3 — clipping.* Clamping the box to the neighbouring lines' baselines removed the
prose but also cut off the denominator, because an inline fraction genuinely reaches into the
vertical band of the line below it. Two expressions on one line also swallowed each other.
**FAILED.**

*Round 4 — what worked.* Three separate rules, each fixing one failure:
1. **Connected, mathematics-only growth.** A glyph joins the box only if it touches the box
   already found, is a mathematics glyph, and does not sit on the expression's own baseline
   (so a box can never creep sideways into the next expression on the same line).
2. **Auxiliary lines are matched back to their host.** A fragment such as a lone `n` or
   `i=1` that lies within 10 pt of a full-width paragraph line, and inside that line
   horizontally, is not a display equation; it belongs to that paragraph's inline
   mathematics and is dropped from the block stream.
3. **Foreign ink is painted out rather than clipped.** Whatever else falls inside the
   rectangle is covered with white before the crop is saved. Only prose is painted, plus
   mathematics that sits on a prose line more than 6 pt from the expression's own baselines,
   so a glyph of the expression can never be erased.

**One more trap.** The first version of the painting erased half of every summation limit.
The extractor reports each character's **full em box**, about 14.5 pt tall for 10 pt text,
not the ink. Painting that box out covered everything between the lines. Painting only the
band from `baseline - 0.78 x size` to `baseline + 0.24 x size` fixed it.

**Status.** SUCCESS after four rounds. Also fixed here: a display equation may contain a
small word ("and", "if", "otherwise"), so the display test became a proportion of
mathematics rather than the absence of prose; and interleaved sub/superscripts
(`_{j}^{R}_{,\lambda}`) are now merged into a single `_{...}^{...}` pair, which removed the
only LaTeX rendering failure in the book.

---

## 2026-08-17 — Entry 009: The transcription workflow, and what it exposed

**Attempt.** 23 agents in parallel, 25 cropped expressions each, reading the images and
writing LaTeX. Each agent was given the characters the PDF text layer gave up (reliable for
symbols, useless for structure), the deterministic LaTeX guess where one existed, and the
sentence preceding the expression. Each agent then ran `src/check_latex.py` on its own output
and fixed anything MathJax refused.

**Result.** 570 expressions written, 0 typesetting failures, 23 of 23 batches returned.

**The valuable part was the agents' own uncertainty reports.** They flagged 40-odd cases as
suspicious, and reading those flags found three real faults in the *extraction*, not in the
transcription:

1. *"crop is only a large left brace"* — repeated a dozen times. A piecewise definition sets
   its arms ("if ith person owns a house") as ordinary words, which the block classifier read
   as prose, so the run broke and the brace became an equation of its own.
2. *"crop image is pixel-identical to m00095 even though extracted_characters implies it
   should be only the numerator"* — an equation number sits on a baseline **between** the
   numerator and the denominator of the fraction it labels, so it split the equation in two
   and both halves then grew back into the same rectangle.
3. Matrices were cut apart the same way, by their own equation number.

**Fixes.**
- The equation number is split off its line before anything is classified.
- A display run absorbs the words set inside it, but only where they start at least 8 pt
  further in than any part of the equation, so an indented paragraph line is never mistaken
  for the arm of a `cases`.
- A display run absorbs its equation number instead of stopping at it.

**Cost of the fix.** Re-extraction changed the crops, but 493 of 554 came out byte for byte
identical, so `src/reuse_transcription.py` matched them on image content and only 61
expressions had to be read again.

**Status.** SUCCESS. Worth recording that the agents' flagged doubts were more useful than
their answers: none of the three faults would have been visible from the LaTeX alone.

---

## 2026-08-17 — Entry 010: Region clipping

**Attempt.** Claim the region above a caption by taking everything whose bounding box lies
*inside* the band between the previous paragraph line and the caption.

**Result.** Table 1.1 lost its header row: "Name | Description" was cut off at the top.

**Why.** The extractor reports each character's full em box, which for the header row starts
slightly above the band. Containment therefore excluded a row that plainly belongs to the
table.

**Fix.** Test for overlap with the band rather than containment, and allow the box to reach
8 pt above it. Same change fixes figures whose topmost axis label sits high.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 011: Tables as markup, and two bad crops

**Attempt.** Convert the 36 tables to real HTML instead of leaving them as pictures, so they
follow the reader's font size. Four agents, nine tables each, each checking its own markup
with `src/check_table_html.py` (well-formed XML, and every row the same width once colspan is
counted).

**Result.** 36 of 36 converted, all parsing, all rectangular. The markup is faithful down to
the minus signs: the agents used U+2212 where the page prints a minus, kept `&lt; 0.0001` with
its space in chapter 3 and without one in chapter 4, exactly as printed.

**Two agents reported that their crop was wrong**, and re-rendered the page themselves to
recover the table. Both were real region-detection faults:

1. **Table 12.3** — the region stopped 190 pt too low. Its row labels sit near the left
   margin and its description column runs the width of the text block, so a table row looked
   exactly like a line of body text and was taken as the top of the region.
   **Fix:** for tables, trust the rules the table is drawn with. The topmost wide horizontal
   rule between the previous caption and this one is the table's top.
2. **Table 12.2** — its column headers are set sideways. Rotated text was skipped outright
   when the page was read, so it contributed nothing to the region and was cropped away.
   **Fix:** rotated lines are dropped from the reading flow but their boxes are kept, so the
   region still covers them.

**Status.** SUCCESS. Worth noting again: the faults were reported by the agents doing the
work, not found by inspection.

---

## 2026-08-17 — Entry 012: Checking the mathematics against the page

**Attempt.** Rather than trust the transcriptions, typeset every one of them with MathJax,
rasterise it, stack it under the crop from the PDF, and give 23 agents the resulting
side-by-side pictures with one instruction: find where the transcription is wrong.

**Why this shape.** Asking a model to re-transcribe and comparing strings is weak: two correct
transcriptions of one expression differ in a dozen harmless ways, and the comparison drowns in
them. Asking "do these two pictures say the same thing?" is a question with a short, checkable
answer, and it is much harder to answer wrongly by accident.

**Three independent checks, not one.**
1. **Symbol census** (free, deterministic). The PDF's text layer loses structure but not
   symbols, so the symbols a transcription claims can be compared against the symbols the page
   contains. It cannot tell a correct fraction from an inverted one, but it catches a dropped
   term for nothing. Result: mean agreement 0.95, and 71% of expressions lose no symbol at all.
2. **Adversarial verification** (23 agents, all 555 expressions).
3. **An independent second opinion** from OpenAI's `codex` command line tool on a sample,
   which is the only figure here not produced by the same model family that did the work.

**Status.** See entry 013 for the result.
