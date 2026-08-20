# Disclaimer

**Read this before you use anything in this repository.**

This is the full statement. The README, the story page and the "About this conversion" page
inside each EPUB carry a short form of it. If the two ever disagree, this file is correct.

| | |
|---|---|
| **Purpose** | Education and experiment. No commercial use. |
| **The book** | Not mine. See [§2](#2-rights-in-the-book) and [`NOTICE`](NOTICE). |
| **The mathematics** | Partly read by AI models. See [§3](#3-the-mathematics-was-read-by-ai-models). |
| **The code and the writing** | Mine, and licensed. See [`LICENSE`](LICENSE) and [`LICENSE-DOCS`](LICENSE-DOCS). |
| **Warranty** | None. See [§6](#6-no-warranty). |

---

## 1. Educational purpose

This repository exists to study one problem: how do you turn a 613-page mathematical textbook,
set in LaTeX and published as a PDF, into an EPUB that reflows on a 7-inch screen?

Use the code, the writing and the two books for personal study, for education and for
experiment.

Do not sell them. Do not include them in a product that you sell. Do not charge for access
to them.

---

## 2. Rights in the book

The book is:

> *An Introduction to Statistical Learning, with Applications in Python*
> Gareth James, Daniela Witten, Trevor Hastie, Robert Tibshirani and Jonathan Taylor
> Springer, 2023. First printing, 5 July 2023.
> **<https://www.statlearning.com/>**

**All rights in the text, the figures, the tables, the mathematics, the exercises and the lab
code stay with the authors and with Springer Nature.**

The authors give the PDF away free of charge at [statlearning.com](https://www.statlearning.com/).
Download it from there. It is the authority. This conversion is not.

This repository changes only the format. It claims nothing over the content, and it grants no
rights over the content. The source PDF is not committed here, and it never will be: see the
comment in [`.gitignore`](.gitignore).

**Takedown.** If you hold rights in the book and you want `output/ISLP.epub` and
`output/ISLP-raster.epub` removed, open an [issue](https://github.com/govarthenan/islp-epub/issues)
or write to <dev@dreamspace.tech>. They will be removed. No argument will be made.

Full statement: [`NOTICE`](NOTICE).

---

## 3. The mathematics was read by AI models

**This is the most important section on this page.** Part of the mathematics in these books
was transcribed by AI vision models. AI models make mistakes. Some of those mistakes are
still in the book.

### What was done by rule, and what was done by a model

The book holds **6,690** distinct mathematical items.

| How it was recovered | Items | Share |
|---|---:|---:|
| **Rebuilt by rule** from the character data in the PDF. No model was used. | 5,974 | 89% |
| **Generated as LaTeX by rule** from the character data, then typeset by MathJax. No model was used. | 185 | 3% |
| **Cropped from the page and read back by an AI vision model**, then typeset by MathJax. | 531 | 8% |

Sub- and superscripts are recorded in a PDF as a font-size drop plus a baseline shift, so most
inline mathematics can be rebuilt exactly, by measurement. A model was used only where the
structure is genuinely absent from the file: fractions, radicals, matrices, integrals and the
display equations.

### How the 531 were checked

1. **Every one of the 531 was checked a second time**, independently, by comparing the printed
   page against the re-typeset candidate side by side. Result: **481 identical, 49 cosmetic
   differences, 1 wrong** — 99.8% agreement. The one error was corrected.
2. **A sample was audited by a different model family.** Every check above was one model family
   checking its own work, so the number it produces is not independent. A sample of 45 was
   handed to OpenAI's `codex` command line tool, which had not seen the earlier answers.
   **44 of 45 agreed. The single disagreement was real**, and no check inside the pipeline had
   caught it: a crop had captured a fraction's denominator and nothing else, and the
   transcription faithfully wrote down what it had been shown. Three faults in the extraction
   code were found and fixed because of it. A repeat audit of 50 expressions after the fix
   found no disagreement.
3. **A symbol census** compared the symbols claimed by each transcription against the symbols
   actually on the page. Mean agreement 0.951.

The detail is in [`work/math_verification.json`](work/math_verification.json), in
[`work/codex_audit.json`](work/codex_audit.json), and in journal entries
[012, 013 and 014](docs/JOURNAL.md).

### What this means for you

* **Check any equation before you rely on it** — for study, for an examination, or for work.
* **The free PDF at [statlearning.com](https://www.statlearning.com/) is the authority.** Open
  it beside the EPUB when an equation matters.
* One error in 531 is a good number, and it is not zero. The checks above measured the error
  rate; they did not remove it.
* Cosmetic differences are expected and are not errors. A model may write `\frac{a}{b}` where
  the book sets a slashed fraction, or choose a different but equivalent spacing command.
* **If you find an error, open an issue** with the
  [equation error form](https://github.com/govarthenan/islp-epub/issues/new?template=math-error.yml).
  A photograph of the page beside the screen is enough. This is the single most useful thing
  anybody can send this project.

The figures, the tables and the lab code were **not** read by a vision model in this way. The
191 figures are re-rendered from the vector art in the PDF at 300 ppi. The 36 tables were
converted to HTML and checked against the page.

---

## 4. Which of the two files to take

One build makes two books from one pass over the PDF. They hold the same words, the same
figures and the same equations. They differ only in how the mathematics is drawn.

| File | Take it if you read with | Mathematics | Size |
|---|---|---|---|
| **`output/ISLP.epub`** | Kobo, Apple Books, Thorium, KOReader, Calibre, Google Play Books | SVG. Sharp at every font size, and the ink follows the reader's colour scheme. | 8.7 MB |
| **`output/ISLP-raster.epub`** | **Moon+ Reader**, Send-to-Kindle, or any reader that shows a small box with the label SVG | The same equations drawn as PNG, at 48 pixels for one em, from the same SVG files. | 11.9 MB |

**If you do not know which one you want, take the first one.** If the equations appear as
small empty boxes, take the second one.

**Why two books exist.** Moon+ Reader on Android draws no SVG at all — not in an image, not
inline, not as a page. It has no MathML either. It shows a small box with the label SVG where
the equation should be. A raster image is the only form it draws. Amazon's Send-to-Kindle
converter also does not always keep SVG, and it does keep a PNG. See journal entry 020.

**A known limit of the raster book.** In a night theme the mathematics may come out black on a
dark page in Moon+ Reader, because Moon+ neither declares a dark colour scheme to the page nor
inverts the screen, so the `filter: invert(1)` rule that serves other readers may not reach it.
Moon+ has a setting that inverts images at night. This is not yet confirmed on a device.

---

## 5. The devices this was tested on

The book was built first for one **Kobo Libra 2**, a 7-inch e-ink reader. Every early decision
was measured against that one panel at 1264 × 1680.

That was not enough. A photograph came back from a **Samsung Galaxy S23 running Moon+ Reader**,
opened at "Notation and Simple Matrix Algebra". Where a matrix should have been there was a
small empty box. That one photograph found the fault, and it is the reason the second book
exists.

A one-page probe EPUB (`src/make_probe_epub.py`) was then built. It shows the same expression
drawn eight different ways, so that a single photograph from any device answers what that
device can and cannot draw.

**So "works on any e-reader" means this:** measured on a Kobo Libra 2 and on a Galaxy S23 with
Moon+ Reader, and reasoned about for everything else. Apple Books, Google Play Books, Thorium,
KOReader, Calibre and Kindle are **expected** to work. They are not **confirmed** to work.

Three questions are still open, and each one needs a person with a device rather than a person
with a keyboard:

1. Moon+ Reader's night theme — does the mathematics read black on a dark page?
2. Dark mode on the Kobo Libra 2 — unchecked.
3. 48 pixels for one em at a large reading font on a real device — is `--pixels-per-em 32`
   good enough? It would save about 2 MB.

Journal entry 020 has the measurements behind all three.

**If your reader shows something wrong, open a
[device report](https://github.com/govarthenan/islp-epub/issues/new?template=device-report.yml).**
See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 6. No warranty

The two EPUB files and the conversion pipeline are supplied as they are.

No promise is made that any expression, figure, table, footnote, index entry or cross-reference
is correct, or that either file opens correctly on any given device or in any given application.

The conversion pipeline in `src/` is supplied under the MIT licence, which disclaims all
warranties. See [`LICENSE`](LICENSE). The same disclaimer of warranty applies to the two EPUB
files in `output/`.

Use your own judgement, and check the free PDF at
[statlearning.com](https://www.statlearning.com/) when it matters.

---

## Where each thing is licensed

| What | Terms | File |
|---|---|---|
| The conversion pipeline in `src/` | MIT | [`LICENSE`](LICENSE) |
| `README.md`, `docs/`, `index.html`, `assets/` | CC BY 4.0 | [`LICENSE-DOCS`](LICENSE-DOCS) |
| The book, and the two EPUB files derived from it | Not licensed. All rights reserved by the authors and Springer Nature. | [`NOTICE`](NOTICE) |

The conversion was done by **Govarthenan Rajadurai**.
