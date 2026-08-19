# ISLP PDF to EPUB — Engineering Journal

Purpose: convert `ISLP_website.pdf` (613 pages, *An Introduction to Statistical Learning with
Applications in Python*) into a reflowable EPUB. It was built first for a Kobo Libra 2
(7 inch, 1264 x 1680 px e-ink), then audited in entry 019 against readers that are not it.

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

---

## 2026-08-17 — Entry 013: The verification result

**Result.** 555 expressions checked, one verdict each:

| verdict  | count | meaning                                                            |
|----------|-------|--------------------------------------------------------------------|
| same     | 500   | the two halves state the same mathematics                          |
| cosmetic |  53   | spacing, delimiter size or font differ; the mathematics does not   |
| wrong    |   2   | the mathematics differs                                            |

**99.6% of the mathematics agrees with the printed page.**

The two that were wrong, and both are worth recording because neither is a misread symbol:

1. `m00567` — the transcription gave only the second row of a two-row equation. The first row,
   `h_1(X) = (0 + X_1 + X_2)^2`, was in the crop and in the character stream and was simply
   not written down.
2. `m00700` — the page prints the matrix in **square** brackets; the transcription used
   `pmatrix`, which sets round ones.

Both corrections were checked to typeset before being accepted; a correction MathJax refuses
would be worse than the original.

**What the 53 cosmetic verdicts were.** Almost all are `\mid` rendering with more space than
the tight `|` the book sets, or MathJax choosing a larger delimiter. One class is worth
noting: several verifiers reported "the TOP crop is itself cut off", which is the extraction's
fault rather than the transcription's, and is honestly recorded as cosmetic rather than being
turned into an invented correction.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 014: What the independent audit caught

**Attempt.** Hand 45 of the comparison images to OpenAI's `codex` command line tool, a
different model family with no sight of the earlier answers, and ask the same question: do
these two halves say the same thing?

**Result.** 44 of 45 agreed (97.8%). The single disagreement was correct and mattered:

> `m00240`: TOP is a fraction with denominator 2!, while BOTTOM is only 2!.

The crop had captured a fraction's denominator and nothing else, and the transcription
faithfully wrote down what it was shown. The verification pass had missed it, because the
candidate really did match what was in the picture — the picture was the problem.

**Three separate causes, all in the extraction:**
1. A fragment is matched back to the paragraph line it belongs to, and a host line had to be
   wider than 200 pt to qualify. **The last line of a paragraph is short by definition**, so
   its inline fractions had their denominators stranded as equations of their own.
2. A fragment counts as belonging to a host only if it sits over that host's mathematics. A
   fraction leaves nothing on the host's own baseline except **its rule**, which is a drawing,
   not a character, so the test failed. Rules now count.
3. Growing a box along whatever mathematics it touched could not tell this expression's
   numerator from the fraction on the line above, and inline fractions on consecutive lines
   genuinely do overlap vertically. Boxes for inline expressions are now built from the
   fragment-to-host assignment made during classification, filtered glyph by glyph so two
   expressions sharing a line do not claim each other's pieces.

**Why this is the entry worth reading.** Every check inside this pipeline was Claude checking
Claude, and all of them passed this expression. The one check from outside the family found it
in a sample of 45. That is the argument for keeping an independent auditor in the loop, not the
argument for a bigger fleet of the same kind.

**Status.** SUCCESS.

---

## 2026-08-17 — Entry 015: Printing an equation twice

**Attempt.** Look for expressions that end up in the EPUB more than once.

**Result.** 26 pairs of near-identical LaTeX on the same page, of which a handful were long
enough to be genuine duplicates rather than a short symbol repeating.

**Why.** An equation with words set inside it —

    minimize { Σ (y_i − β_0 − Σ β_j x_ij)² }   subject to   Σ I(β_j ≠ 0) ≤ s

— reads to the classifier as a paragraph, because "minimize", "subject to" and the sentence
that follows are prose. The paragraph's own inline images then hold the whole equation. But
the same pixels also produced display blocks from the lines that carry only symbols, so the
equation was typeset twice: once inside the sentence and once as a centred display.

**Fix.** Before anything is registered, the inline expressions on a page are measured, and any
display block that one of them already covers by 40% or more of its area is dropped. The
paragraph rendering wins, because it is the one that carries the words.

**Status.** SUCCESS.

**Known limits, recorded honestly.** A handful of expressions that wrap across a line break
leave a small fragment at the right edge of the column, which renders as a little image of its
own. There are a few of these in 613 pages and the content is not lost, only set apart.

---

## 2026-08-17 — Entry 016: Converged

**The extraction stopped changing.** After the last round of fixes, re-extracting the
mathematics produced 531 crops of which **531 were byte for byte identical** to the previous
round: nothing left to read again.

**Final verification, over all 531 expressions:**

| verdict  | count | share |
|----------|-------|-------|
| same     |  481  | 90.6% |
| cosmetic |   49  |  9.2% |
| wrong    |    1  |  0.2% |

**99.8% of the mathematics agrees with the printed page.** The single error was a missing
trailing full stop, which was corrected.

**Three checks, three different kinds of evidence:**
- symbol census (deterministic, free): mean agreement 0.951; 71.5% of expressions lose no
  symbol at all;
- adversarial verification (23 agents, every expression): 99.8%;
- independent audit through OpenAI's `codex`, on a sample, from outside the model family.

**Also fixed in this round, from reading the rendered pages rather than the numbers:**
- Exercises run to three levels — `1.`, `(a)`, `i.` — and the roman level was missing from the
  marker pattern, so its items ran into the paragraph above. Depth now comes from the marker
  itself, not from the left margin, which drifts twenty points between items in one list.
- "Python-based" was closing up to "Pythonbased". The vocabulary tokenised on letters only, so
  "trade-off" was stored as two words and the hyphenated form could never be confirmed;
  every broken word was being closed up by default.

---

## 2026-08-17 — Entry 017: The last four figures

**Attempt.** Check that every figure caption has a picture. 191 captions, 187 pictures.

**Result.** The four missing ones (6.7, 10.5, 10.6, 10.9) are precisely the figures in this
book that are **raster images** rather than vector art. The extraction flags were written out
explicitly and left out `TEXT_PRESERVE_IMAGES`, so no image block was reported at all and the
region finder had nothing to find.

**Status.** SUCCESS. 191 of 191.

---

## 2026-08-17 — Entry 018: Final numbers

| | |
|---|---|
| Pages read | 613 |
| Documents in the spine | 15 chapters and matter, plus cover |
| Paragraphs rebuilt | 3,297 |
| Lab code cells | 1,137 |
| Figures | 191 |
| Tables, as reflowing markup | 36 |
| Display equations | 409 |
| Mathematics as plain HTML | 5,974 runs |
| Mathematics as SVG | 716 expressions |
| Mathematics as a bitmap | 0 |
| Cross-references resolved | 3,686 of 3,686 |
| EPUB | 8.2 MB, EPUB 3 with NCX, structurally valid |

**Accuracy of the mathematics**

| check | scope | result |
|---|---|---|
| symbol census (deterministic) | 484 scorable | mean agreement 0.951; 71.5% lose no symbol |
| adversarial verification | all 531 | 99.8% agree with the page |
| independent audit via OpenAI codex | sample of 50 | 50 of 50 agree |

**What would be worth doing next**, in order of value:
1. A handful of expressions that wrap across a line break leave a small fragment rendered as
   its own image. Handling a wrapped expression as one unit would tidy those.
2. The index's page numbers are links, and they resolve, but an index entry pointing at a
   paragraph rather than at the term itself is coarser than the printed page reference.
3. A `.kepub.epub` variant would give Kobo its own per-chapter page counts. The plain EPUB
   reads correctly without it.

---

## 2026-08-19 — Entry 019: A device audit before publishing

The book was built for one Kobo Libra 2. Before putting it in front of other people, every
choice made for that panel was measured against readers that are not it.

**Finding 1 — the mathematics was always black.** Each expression is a file referenced with
`<img src="…svg">`, and MathJax draws in `currentColor`. An `<img>` is a separate document,
so `currentColor` resolves against the SVG's own root and not against the page. Measured in
a browser, on a page painted `#1b1b1b` with `#e8e8e8` text, the ink came back `rgb(0,0,0)`:
a contrast ratio of **1.22:1**. The e-ink devices never showed this, because they invert the
whole screen rather than repaint it with CSS; a reader that themes with CSS — Thorium,
Apple Books, Calibre's viewer — showed invisible mathematics.

*Fixed* by giving each SVG two rules of its own:
`svg{color:#000}` and `@media (prefers-color-scheme:dark){svg{color:#fff}}`. An SVG used as
an image takes its colour scheme from the element that holds it, so this works where the
page-level rule cannot reach. Re-measured: `rgb(255,255,255)`, **17.22:1**. A reader that
inverts the screen matches neither rule, keeps the black, and inverts it as before.

**Finding 2 — the code cells disappeared with it.** `pre.input` set `background: #f4f4f4`
and no `color`. In a CSS-themed dark reader the inherited text colour became near-white on
a near-white block: **1.11:1**, across 1,137 code cells. *Fixed* by never setting a
background without its foreground, and by adding a `prefers-color-scheme` block. Re-measured
at **17.17:1**. Margin notes had the same fault at `color: #555` (**2.31:1** on a dark page)
and now use `opacity` instead, which is correct in any theme.

**Finding 3 — grey figures destroyed the series.** The book plots one series in orange
`rgb(152,65,0)` and the next in blue `rgb(0,104,180)`. Their luminances are 84 and 82 of
255. Quantised to 16 greys both landed on the same value — sampled on figure 10.10, blue and
orange both came back as grey 101. Every two-colour plot in the book was a single shade.

*Fixed* by rendering figures in colour with a 64-entry adaptive palette. The cost is small,
because these are line drawings on white: images 5.5 MB → 6.5 MB, the EPUB 8.2 MB → 9.1 MB.
A grey e-ink screen converts the colour itself and is no worse off than before; every colour
device now gets the figures as printed. 187 of the 192 images carry colour; five were
monochrome to begin with.

**Smaller things.** Code was set at `0.68em`. Measured against the book's own content — the
longest line is 89 characters, the median 41 — that size fits 159 characters across a Kobo
column, more than twice what is needed. Raised to `0.8em`, which still fits 84 characters at
the largest Kobo font and is far kinder on a phone. Hyphenation is now asked for in four
spellings, so Adobe-based readers hyphenate too rather than opening rivers in a justified
narrow column. Figures and the cover take a `max-height` in `vh`, so a short or landscape
screen cannot push one off the page. The identifier was `urn:uuid:islp-python-1st-edition-reflow`,
which is not a UUID; it is now a real uuid5 of the repository URL, fixed so that a rebuild
keeps the same book identity. EPUB Accessibility 1.1 metadata was added, and its summary
says plainly that the mathematics carries LaTeX in its alternative text rather than MathML.

**Still open.** The mathematics is SVG, and Amazon's Send-to-Kindle converter does not always
keep SVG. That needs a real Kindle to settle. Dark mode on the Libra 2 itself should be
checked once after this change, to confirm Kobo inverts the screen rather than declaring a
dark colour scheme; if it declares one, the mathematics would invert twice and the two rules
inside the SVG files should come out again.

---

## 2026-08-19 — Entry 020: The reader that draws no SVG

Entry 019 closed with the mathematics as SVG and one worry written down: Amazon's converter
does not always keep SVG. The worry was too narrow. A photograph came back from a Samsung
phone running Moon+ Reader, opened at "Notation and Simple Matrix Algebra". Where the matrix
should be there was a small box with the label `SVG`.

**Finding — Moon+ Reader draws no SVG at all.** Not in an `<img>`, not inline, not as a page
of its own. The DAISY EPUB 3 support grid records all three as "Not Supported", and the
reader does not use a browser engine, which is why. That is 716 files, referenced 926 times:
409 display equations and 517 inline expressions. The 5,974 runs the pipeline already writes
as HTML text were drawn correctly, which is why the words around the hole looked right.

**No markup fixes this.** MathML is the EPUB 3 standard for mathematics, and the same grid
marks every MathML test for this reader "Not Tested", so it was tested here instead: it came
out as flat text, `A∈ℝr×d`, with no layout at all. LaTeX source is typeset by no reader.
MathJax as a script does not run, because readers switch scripting off. And even a reader
that did draw MathML would not settle it, because the Kobo Libra 2 this book was built for
draws SVG and not MathML, and one EPUB cannot choose its markup per reader.

**A probe before a rebuild.** Rather than guess, a one-page EPUB was built with the same
expression drawn eight ways, each row labelled, and opened on the phone. One photograph
settled everything. The SVG row failed, as expected. A PNG forced to one em and the same file
forced to three em came out at the right sizes, which was the answer that mattered: **Moon+
does obey a size in `em` on an image**, so a PNG still grows with the reader's font. A
transparent background blended into the cream page where a white one showed as a bright
block. The wide matrix fitted the page. An inline PNG sat on the line of text.

**Two books, not one.** The SVG book is not broken; it is sharp at every font size and its
ink follows the reader's colour scheme. So the build now writes both from one pass over the
PDF: `ISLP.epub` with SVG, and `ISLP-raster.epub` with the same expressions drawn as PNG at
48 pixels for one em. The PNG is made from the SVG, never from the page, so the two books
cannot disagree about what an equation says.

**The bracket bug, and the check that missed it.** The first raster book was drawn with
MuPDF, which the project already depended on. Three checks passed: every one of the 716
equations carried ink; replacing each `<use>` with the glyph it points at changed nothing;
removing the glyph definitions emptied the image. Then the phone came back with a second
photograph, and the brackets around the matrices were wrong — a hook, a straight bar that did
not join it, and another hook.

The cause is one construct. MathJax stretches a tall bracket by putting its middle piece in a
nested `<svg>` with its own viewport, and scaling that piece to the height it needs:

```xml
<svg width="875" height="2369.2" y="-934.6" x="0" viewBox="0 535 875 2369.2">
  <use xlink:href="#MJX-2-TEX-S4-239F" transform="scale(1,5.732)"/>
</svg>
```

MuPDF puts that viewport in the wrong place. CairoSVG draws it the way a browser does, so the
raster book is drawn by CairoSVG now. 40 of the 716 equations stretch a bracket that way, and
all 40 were checked by eye on one sheet. A third photograph from the phone confirmed the fix.

The lesson is about the checks, not the renderer. All three compared a renderer against
itself, so all three passed while every matrix bracket was broken. Drawing each equation a
second time with MuPDF and comparing the two was tried as an automatic test and dropped: over
60 equations, ordinary ones differ from each other by as much as 0.82 of their ink, only from
how the two renderers smooth an edge, while the broken brackets differed by 0.13 to 0.33. A
test that reports 58 faults out of 60 hides the one that is real. What replaced it is smaller
and honest: every equation that stretches a bracket is drawn onto one sheet for a person to
look at. A person found this bug; a person is what the check now asks for.

**Cost.** The raster book is 11.9 MB against 8.7 MB. The PNG files are 5.5 MB against 6.2 MB
of SVG, and the gap widens in the archive because SVG is text and compresses while a PNG does
not.

**Still open.** Moon+ Reader's night theme. It neither declares a dark colour scheme to the
page nor inverts the screen, so the `filter: invert(1)` that serves Thorium, Apple Books and
Calibre may not reach it, and the mathematics would read black on a dark page. Moon+ has a
setting that inverts images at night. This needs one more look at the phone. Dark mode on the
Libra 2 is still unchecked, as entry 019 left it.
