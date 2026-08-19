"""Draw a standalone MathJax SVG as a transparent PNG.

Moon+ Reader on Android, and the Amazon Send-to-Kindle converter, do not draw SVG. The book
is therefore also built with its mathematics as raster images, from these same SVG files, so
the two builds can never disagree about what an equation says.

The drawing is done by CairoSVG, not by MuPDF, and the reason matters. MathJax stretches a
tall bracket by putting the middle piece of the bracket inside a nested `<svg>` that has its
own viewport, and by scaling that piece to the height it needs:

    <svg width="875" height="2369.2" y="-934.6" x="0" viewBox="0 535 875 2369.2">
      <use xlink:href="#MJX-2-TEX-S4-239F" transform="scale(1,5.732)"/>
    </svg>

MuPDF does not place that nested viewport correctly. Every bracket around a matrix came out
as a hook, a straight bar that did not join it, and another hook. CairoSVG draws the same
files the way a browser does. `svg_to_png_mupdf` is kept so that the two can be compared
against each other in `src/check_math_raster.py`: two renderers that agree are good evidence,
and where they disagree a person looks.

MathJax gives each file a width and a height in `ex`, and writes one em as two ex
(`EX_PER_EM` in `src/render_math.cjs`). The pixel size therefore follows from those
attributes alone, and no caller has to work it out.
"""

from __future__ import annotations

import io
import re

import cairosvg
import pymupdf
from PIL import Image

# Named in work/math_png_cache.json, so that a change of renderer throws the drawings away.
RASTER_RENDERER = "cairosvg"

EX_PER_EM = 2.0  # MathJax's own metric; see src/render_math.cjs
MUPDF_POINTS_PER_EM = 12.0  # MuPDF fixes the ex at 6 points, and there are 2 ex to the em

ROOT_SIZE_RE = re.compile(rb'<svg\b[^>]*?\bwidth="(-?[\d.]+)ex"[^>]*?\bheight="(-?[\d.]+)ex"')


def size_in_em(svg_bytes: bytes) -> tuple[float, float]:
    """The width and the height the file asks for, in em.

    Raises:
        ValueError: if the root element does not carry a width and a height in `ex`, which
            would mean the file did not come from `src/render_math.cjs`.
    """
    match = ROOT_SIZE_RE.search(svg_bytes[:2048])
    if not match:
        raise ValueError("the SVG root has no width and height in ex")
    return float(match.group(1)) / EX_PER_EM, float(match.group(2)) / EX_PER_EM


def svg_to_png(svg_bytes: bytes, pixels_per_em: int) -> bytes:
    """Draw one equation at a fixed number of pixels per em.

    Args:
        svg_bytes: The complete SVG file, as written by `src/render_math.cjs`.
        pixels_per_em: Pixels to use for one CSS em of the reader's text.

    Returns:
        The PNG file, grey plus alpha, with a transparent background.
    """
    width_em, height_em = size_in_em(svg_bytes)
    png = cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=max(1, round(width_em * pixels_per_em)),
        output_height=max(1, round(height_em * pixels_per_em)),
    )
    # The ink is pure black on a clear background, so there is no colour to keep. Grey plus
    # alpha is about a quarter smaller, and quantising the alpha would break a thin stroke.
    image = Image.open(io.BytesIO(png)).convert("LA")
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def svg_to_png_on_white(svg_bytes: bytes, pixels_per_em: int) -> bytes:
    """Draw one equation on an opaque white background, for the probe EPUB only.

    A reader that neither declares a dark colour scheme nor inverts the screen shows black
    ink on a dark page, which cannot be read. A white background is legible everywhere, at
    the cost of a bright block on a cream or dark page. The probe compares the two.
    """
    width_em, height_em = size_in_em(svg_bytes)
    png = cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=max(1, round(width_em * pixels_per_em)),
        output_height=max(1, round(height_em * pixels_per_em)),
        background_color="white",
    )
    buffer = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("L").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def svg_to_png_mupdf(svg_bytes: bytes, pixels_per_em: int) -> bytes:
    """Draw one equation with MuPDF, as a second opinion for the checks.

    This is not used to build the book. MuPDF misplaces the nested viewport that MathJax uses
    to stretch a tall bracket, so its drawing of a matrix is wrong. It is still a renderer
    written by different people, and it agrees with CairoSVG everywhere else, which makes a
    disagreement between the two worth looking at.
    """
    document = pymupdf.open(stream=svg_bytes, filetype="svg")
    pixmap = document[0].get_pixmap(dpi=round(pixels_per_em * 72 / MUPDF_POINTS_PER_EM), alpha=True)
    image = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples).convert("LA")
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
