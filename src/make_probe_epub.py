"""Write a one-page EPUB that tests how a reader draws mathematics.

    uv run python src/make_probe_epub.py --out /path/to/probe.epub

Moon+ Reader on Android draws a placeholder box instead of an SVG equation. Before the whole
book is rebuilt with raster mathematics, this probe answers the questions that decide how the
raster is made. It holds one page of labelled specimens. Open it on the device, photograph
the page, and read the answers from the labels.

The probe uses the real `EpubBuilder` and the real `svg_to_png`, not a copy of them, so what
it measures is what the book will do.

`--out` has no default on purpose: the probe must never be written into `output/`, which
holds the books that are published.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from islp.epub import EpubBuilder, NavPoint
from islp.mathraster import svg_to_png, svg_to_png_on_white

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

PIXELS_PER_EM = 48

# A short expression and a wide one, both taken from the book itself.
SMALL = "m00013"  # \mathbf{A} \in \mathbb{R}^{r\times d}
WIDE = "m00001"  # the matrix X of chapter 2, the equation in the photograph

# Hand-written MathML for the small expression. MathML is the EPUB 3 standard for
# mathematics. The support grid marks every MathML test for Moon+ Reader "Not Tested", so
# this row closes that gap with evidence. It cannot become the form the book ships, because
# the Kobo Libra 2 draws SVG and not MathML.
MATHML = (
    '<math xmlns="http://www.w3.org/1998/Math/MathML">'
    "<mi>A</mi><mo>&#8712;</mo>"
    "<msup><mi>&#8477;</mi><mrow><mi>r</mi><mo>&#215;</mo><mi>d</mi></mrow></msup>"
    "</math>"
)

PROBE_CSS = """
p.probe-label { text-indent: 0; font-weight: bold; margin: 1.1em 0 0.2em; text-align: left; }
p.probe-note { text-indent: 0; font-size: 0.8em; font-style: italic; margin: 0.2em 0 0;
               text-align: left; }
p.probe-row { text-indent: 0; margin: 0.2em 0; text-align: left; }
/* A tint behind row E, so a white background on an image shows as a block rather than
   disappearing into a white page. The foreground is set with it, as everywhere else. */
p.probe-tint { text-indent: 0; margin: 0.2em 0; text-align: left;
               background: #e6ddc6; color: #1a1a1a; padding: 0.4em 0.3em; }
hr.probe { border: 0; border-top: 1px solid #999; margin: 0.4em 0 0; }
"""


def specimen(label: str, markup: str, note: str, row_class: str = "probe-row") -> str:
    """One labelled row: what it is, the thing itself, and what it should look like."""
    return (
        f'<p class="probe-label">{label}</p>'
        f'<p class="{row_class}">{markup}</p>'
        f'<p class="probe-note">{note}</p>'
        '<hr class="probe"/>'
    )


def build_body(manifest: dict[str, dict]) -> str:
    small = manifest[SMALL]
    wide = manifest[WIDE]
    small_height = small["heightEm"]
    wide_width = wide["widthEm"]

    parts = [
        "<h1>Mathematics probe</h1>",
        '<p class="noindent">Every row below holds the same expression, drawn a different '
        "way. Photograph this page. For each row, note whether it is visible, whether it can "
        "be read, and how large it is.</p>",
        specimen(
            "A. SVG through an image tag. This is what the book does now.",
            f'<img src="../math/{SMALL}.svg" alt="A in R^(r x d)" '
            f'style="height:{small_height:.3f}em;vertical-align:-0.045em"/>',
            "Expected to fail on Moon+ Reader: a small box with the label SVG.",
        ),
        specimen(
            "B. PNG, no size given. Drawn at 48 pixels for one em.",
            f'<img src="../math/{SMALL}-a.png" alt="A in R^(r x d)"/>',
            "The size to compare rows C and D against.",
        ),
        specimen(
            "C. The same PNG file, forced to one em high.",
            f'<img src="../math/{SMALL}-a.png" alt="A in R^(r x d)" style="height:1em"/>',
            "Should be about as tall as this line of text.",
        ),
        specimen(
            "D. The same PNG file again, forced to three em high.",
            f'<img src="../math/{SMALL}-a.png" alt="A in R^(r x d)" style="height:3em"/>',
            "Should be three times taller than row C. If B, C and D are all the same size, "
            "the reader ignores the size in the style, and the images must instead be made "
            "at the size they are shown.",
        ),
        specimen(
            "E. Transparent background, then white background, on a tinted block.",
            f'<img src="../math/{SMALL}-a.png" alt="transparent" style="height:2em"/>'
            "&#160;&#160;&#160;&#160;"
            f'<img src="../math/{SMALL}-b.png" alt="white" style="height:2em"/>',
            "The left one should blend into the tint. The right one should show as a bright "
            "block. Now switch the reader to its night theme and look again: on a dark page "
            "the left one may become black on black, and the right one stays readable.",
            "probe-tint",
        ),
        specimen(
            "F. A wide display equation. The matrix from the photograph.",
            f'<div class="eq"><img src="../math/{WIDE}-a.png" alt="matrix X" style="width:{wide_width:.3f}em"/></div>',
            "Should fit inside the page width, not run off the right edge.",
        ),
        specimen(
            "G. MathML, the EPUB 3 standard for mathematics.",
            MATHML,
            "If this row is drawn correctly, the reader supports MathML.",
        ),
        specimen(
            "H. The PNG inside a sentence, as an inline expression.",
            "We let "
            f'<img class="mi" src="../math/{SMALL}-a.png" alt="A in R^(r x d)" '
            f'style="height:{small_height:.3f}em;vertical-align:-0.045em"/>'
            " denote the matrix, and read on to the end of the line to see whether the line "
            "spacing stays even.",
            "The image should sit on the line of text, not above or below it.",
        ),
    ]
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="where to write the probe; never output/")
    parser.add_argument("--pixels-per-em", type=int, default=PIXELS_PER_EM)
    args = parser.parse_args()

    target = Path(args.out).resolve()
    if target.parent == (ROOT / "output"):
        parser.error("the probe must not be written into output/, which holds the published books")

    manifest = json.loads((WORK / "math_svg_manifest.json").read_text())["manifest"]
    builder = EpubBuilder(identifier="urn:uuid:0d0f0a3e-0000-4000-8000-000000000001", title="Mathematics probe")
    builder.authors = ["Govarthenan Rajadurai"]
    builder.description = "A one-page test of how a reader draws mathematics."
    builder.extra_css = PROBE_CSS

    for ident in (SMALL, WIDE):
        svg_bytes = (WORK / "math_svg" / manifest[ident]["file"]).read_bytes()
        builder.add_resource(f"math/{ident}.svg", "image/svg+xml", svg_bytes, f"svg-{ident}")
        builder.add_resource(
            f"math/{ident}-a.png", "image/png", svg_to_png(svg_bytes, args.pixels_per_em), f"png-{ident}-a"
        )
        builder.add_resource(
            f"math/{ident}-b.png", "image/png", svg_to_png_on_white(svg_bytes, args.pixels_per_em), f"png-{ident}-b"
        )

    builder.add_document("probe.xhtml", "Mathematics probe", build_body(manifest), "probe", properties="mathml")
    builder.nav.append(NavPoint("Mathematics probe", "text/probe.xhtml", 1))
    builder.bodymatter_href = "text/probe.xhtml"
    builder.write(target)
    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
