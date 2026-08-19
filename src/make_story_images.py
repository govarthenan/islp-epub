"""Produce the before/after pictures used by index.html to tell the cropping story.

    uv run python src/make_story_images.py

Renders the same inline fraction four ways -- the box taken from one text line, a box grown
greedily, a box clamped to the neighbouring baselines, and the box the finished pipeline
produces -- then the masking pair that shows why a rectangle alone is not enough.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from build_epub import render_crop  # noqa: E402
from islp.blocks import assemble  # noqa: E402
from islp.figures import expand_math_bbox, inline_math_bbox  # noqa: E402
from islp.inline import Tier, build_inline  # noqa: E402
from islp.pagemodel import load_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SLICE_PAGE = 84  # zero based: printed page 75, the t-statistic, a tall fraction
MASK_PAGE = 80  # zero based: printed page 71, a fraction set inside a sentence


def save(data: bytes, name: str) -> None:
    image = Image.open(io.BytesIO(data)).convert("L")
    if image.width > 900:
        factor = 900 / image.width
        image = image.resize((900, max(1, int(image.height * factor))), Image.LANCZOS)
    image.save(ASSETS / name, optimize=True)
    print(f"{name}: {image.size}")


def pick_flattest(page):
    """The flattest box on the page: a tall fraction whose glyphs the text layer filed on
    three different lines, so a box taken from one line is only a slice of it."""
    target, best = None, 1e9
    for line in page.lines:
        for run in build_inline(line.chars, page.drawing_rects).math_runs:
            if run.tier != Tier.VLM or run.bbox[2] - run.bbox[0] < 30:
                continue
            height = run.bbox[3] - run.bbox[1]
            if height < best:
                best, target = height, (line, run)
    return target


def pick_in_sentence(page):
    """A fraction sitting inside a line of prose: the case where the crop unavoidably catches
    ink from the line below, and painting it out is the only clean answer."""
    for line in page.lines:
        if "where" not in line.text:
            continue
        for run in build_inline(line.chars, page.drawing_rects).math_runs:
            if run.tier == Tier.VLM and run.bbox[2] - run.bbox[0] > 40:
                return line, run
    return None


def clamp_to_neighbours(page, line, bbox):
    """Attempt 3: stop the box at the baselines of the lines above and below.

    The extractor files a fraction's numerator, rule and denominator as three separate
    lines, so "the line below" is the denominator's own baseline and the cut lands inside
    the expression.
    """
    above = max((v.baseline for v in page.lines if v.baseline < line.baseline), default=bbox[1])
    below = min((v.baseline for v in page.lines if v.baseline > line.baseline), default=bbox[3])
    return (bbox[0], max(bbox[1], above), bbox[2], min(bbox[3], below))


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    pdf = pymupdf.open(ROOT / "ISLP_website.pdf")

    page = load_page(pdf, SLICE_PAGE)
    line, run = pick_flattest(page)
    save(render_crop(pdf[SLICE_PAGE], run.bbox, 300, pad=1), "crop-1-line-box.png")
    greedy = (run.bbox[0] - 4, run.bbox[1] - 22, run.bbox[2] + 60, run.bbox[3] + 22)
    save(render_crop(pdf[SLICE_PAGE], greedy, 300, pad=1), "crop-2-greedy.png")
    grown, _ = expand_math_bbox(page, run.bbox, [line.baseline], run.chars)
    clamped = clamp_to_neighbours(page, line, grown)
    save(render_crop(pdf[SLICE_PAGE], clamped, 300, pad=1), "crop-3-clamped.png")
    save(render_crop(pdf[SLICE_PAGE], grown, 300, pad=1), "crop-4-grown.png")

    page = load_page(pdf, MASK_PAGE)
    assemble(page)  # fills page.auxiliary, the fragment-to-host assignment
    line, run = pick_in_sentence(page)
    grown, foreign = inline_math_bbox(page, line, run.chars, page.drawing_rects)
    save(render_crop(pdf[MASK_PAGE], grown, 300, pad=1), "crop-5-unmasked.png")
    save(render_crop(pdf[MASK_PAGE], grown, 300, pad=1, foreign_ink=foreign), "crop-6-masked.png")


if __name__ == "__main__":
    main()
