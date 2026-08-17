"""Locate and render figures and tables.

Almost every figure in this book is vector art, so nothing useful comes out of
`pdfimages`. Instead each figure is found as the graphic region directly above its caption
and re-rendered from the PDF at a resolution suited to the Kobo Libra 2 screen
(1264 x 1680 px, 300 ppi).

Tables are handled the same way. Their rows are ordinary text, so if they were left in the
text stream they would come out as nonsense paragraphs; the region is claimed first and the
lines inside it are consumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

from .pagemodel import Page, VLine, Zone

CAPTION_RE = re.compile(r"^\s*(FIGURE|TABLE)\s+([A-Z]?\.?\d+\.\d+)\.")
CONTENT_X0 = 45.0
CONTENT_X1 = 475.0
TOP_MARGIN = 50.0
BOTTOM_MARGIN = 660.0


@dataclass
class Region:
    kind: str  # "figure" | "table"
    number: str
    bbox: tuple[float, float, float, float]
    caption_bbox: tuple[float, float, float, float]
    page: int


def _union(boxes):
    boxes = list(boxes)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _caption_lines(page: Page):
    for line in page.lines:
        if line.zone != Zone.MAIN:
            continue
        match = CAPTION_RE.match(line.text.strip())
        if match:
            yield line, match.group(1).lower(), match.group(2)


def _caption_bottom(page: Page, first: VLine) -> float:
    """How far down the page a caption runs: its own line plus the lines that continue it, all
    set at the same smaller size."""
    bottom = first.y1
    previous = first
    for other in sorted(page.lines, key=lambda ln: ln.baseline):
        if other.baseline <= previous.baseline + 0.1:
            continue
        if other.zone not in (Zone.MAIN, Zone.CODE):
            continue
        if abs(other.size - first.size) > 0.6:
            break
        if other.baseline - previous.baseline > 16.0:
            break
        bottom = max(bottom, other.y1)
        previous = other
    return bottom


def _ruled_table_boxes(pdf_page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    try:
        finder = pdf_page.find_tables(strategy="lines_strict")
    except Exception:
        return []
    return [tuple(table.bbox) for table in finder.tables]


def detect_regions(page: Page, pdf_page: pymupdf.Page) -> list[Region]:
    """One region per caption: the block of graphics or table rows sitting above it."""
    regions: list[Region] = []
    ruled = _ruled_table_boxes(pdf_page)
    captions = list(_caption_lines(page))
    caption_extents = [(line.y0, _caption_bottom(page, line)) for line, _, _ in captions]

    for line, kind, number in captions:
        caption_top = line.y0
        # The region cannot reach above the previous caption, and must clear the whole of it:
        # a caption runs to several lines, and stopping at its first line left the previous
        # figure's caption sitting inside this figure's picture.
        floor = TOP_MARGIN
        for other_top, other_bottom in caption_extents:
            if other_top < caption_top - 4:
                floor = max(floor, other_bottom)

        caption_floor = floor
        # a body-text line above the caption ends the region
        for other in page.lines:
            if other is line or other.zone != Zone.MAIN:
                continue
            if other.y1 <= caption_top - 2 and other.y1 > floor:
                if other.x0 <= 102.5 and other.x1 - other.x0 > 200 and other.size >= 9.5:
                    floor = max(floor, other.y1)

        if kind == "table":
            # A table's row labels sit near the left margin and its descriptions run the
            # width of the column, so a row can look exactly like a line of body text. The
            # rules the table is drawn with do not lie: the topmost one is its top.
            rule_tops = [rect[1] for rect in page.drawing_rects
                         if rect[3] - rect[1] <= 2.0 and rect[2] - rect[0] > 150
                         and caption_floor < rect[1] < caption_top - 4]
            if rule_tops and min(rule_tops) - 3 < floor:
                floor = max(caption_floor, min(rule_tops) - 3)

        band = (floor + 1.0, caption_top - 1.0)
        if band[1] - band[0] < 8:
            continue

        pieces: list[tuple[float, float, float, float]] = []
        # Overlap, not containment: a header row whose glyph boxes start a little above the
        # band still belongs to the table, and testing containment clipped it away.
        for rect in page.drawing_rects + page.image_rects + page.rotated_rects:
            if rect[3] > band[0] and rect[1] < band[1] and rect[0] >= CONTENT_X0:
                if rect[2] - rect[0] > 0.2 and rect[3] - rect[1] > 0.2:
                    pieces.append(rect)
        for other in page.lines:
            if other is line:
                continue
            if other.zone in (Zone.HEADER, Zone.FOOTER, Zone.MARGIN):
                continue
            if other.y1 > band[0] and other.y0 < band[1]:
                pieces.append(other.bbox)
        for box in ruled:
            if box[1] >= band[0] - 6 and box[3] <= band[1] + 6:
                pieces.append(box)

        bbox = _union(pieces)
        if bbox is None:
            continue
        bbox = (
            max(CONTENT_X0, bbox[0] - 4),
            max(band[0] - 8, bbox[1] - 4),
            min(CONTENT_X1, bbox[2] + 4),
            min(band[1] + 2, bbox[3] + 4),
        )
        if bbox[2] - bbox[0] < 20 or bbox[3] - bbox[1] < 12:
            continue
        regions.append(Region(kind=kind, number=number, bbox=bbox,
                              caption_bbox=line.bbox, page=page.index))
    return regions


def consume_lines(page: Page, regions: list[Region]) -> None:
    """Mark every text line that falls inside a figure or table region as graphic, so it does
    not reappear as a paragraph."""
    for line in page.lines:
        # Table row labels are set in a typewriter font, so they are tagged as code; they must
        # still be claimed by the region they sit in.
        if line.zone not in (Zone.MAIN, Zone.CODE):
            continue
        if CAPTION_RE.match(line.text.strip()):
            continue
        centre_y = (line.y0 + line.y1) / 2
        for region in regions:
            x0, y0, x1, y1 = region.bbox
            if y0 - 1 <= centre_y <= y1 + 1 and line.x0 >= x0 - 6 and line.x1 <= x1 + 6:
                line.zone = Zone.GRAPHIC
                break


def render_region(pdf_page: pymupdf.Page, bbox, dpi: int = 300,
                  colour: bool = False) -> pymupdf.Pixmap:
    clip = pymupdf.Rect(*bbox)
    colorspace = pymupdf.csRGB if colour else pymupdf.csGRAY
    return pdf_page.get_pixmap(dpi=dpi, clip=clip, colorspace=colorspace, alpha=False)


# ------------------------------------------------------------------------------------------
# growing a mathematics box to its true extent
# ------------------------------------------------------------------------------------------

from .fonts import Role  # noqa: E402

DOT_GLYPHS = ".\u00b7\u2026\u22ee\u22ef\u22f1"
NEIGHBOUR_GAP = 4.0
BASELINE_TOLERANCE = 1.5
MAX_VERTICAL_GROWTH = 40.0


EQUATION_NUMBER_RE = re.compile(r"^\(\d+\.\d+\)$")


def _is_equation_number(line) -> bool:
    return bool(EQUATION_NUMBER_RE.match(line.text.strip())) and line.x0 > 378.0


def _has_prose_word(line) -> bool:
    text = "".join(c.c for c in line.chars
                   if c.role in (Role.PROSE, Role.PROSE_ITALIC, Role.PROSE_BOLD))
    return bool(re.search(r"[A-Za-z]{2,}", text))


def expand_math_bbox(page: Page, bbox: tuple[float, float, float, float],
                     baselines: list[float] | None = None,
                     own_chars: list | None = None,
                     max_growth: float = MAX_VERTICAL_GROWTH):
    """Grow a box until it holds the whole expression.

    A fraction, a radical or a large operator puts glyphs on baselines of their own, and the
    text extractor files those on separate lines, so a box taken from one line cuts a
    fraction in half. Growth is deliberately narrow:

      * only mathematics glyphs and the dots of an ellipsis are absorbed;
      * nothing is absorbed from a line that carries a word of prose, which is what stops the
        box from running into the paragraph above or below;
      * a glyph sitting on the expression's own baseline can never widen the box, which is
        what stops one expression from swallowing the next one on the same line.
    """
    x0, y0, x1, y1 = bbox
    origin_height = bbox[3] - bbox[1]
    own_baselines = list(baselines or [])
    kept: set[int] = {id(char) for char in (own_chars or [])}

    candidates = []
    for line in page.lines:
        if line.zone in (Zone.HEADER, Zone.FOOTER, Zone.MARGIN):
            continue
        if _is_equation_number(line):
            continue
        prose_line = _has_prose_word(line)
        for char in line.chars:
            if char.is_space:
                continue
            if char.role not in (Role.MATH_VAR, Role.MATH_UP) and char.c not in DOT_GLYPHS:
                continue
            on_own_baseline = any(abs(char.oy - base) < BASELINE_TOLERANCE for base in own_baselines)
            if prose_line and not on_own_baseline:
                continue
            candidates.append((char, on_own_baseline))

    rules = [rect for rect in page.drawing_rects
             if rect[3] - rect[1] <= 2.0 and rect[2] - rect[0] <= 220]

    for _ in range(8):
        changed = False
        for char, on_own_baseline in candidates:
            if char.x0 > x1 + 2 or char.x1 < x0 - 2:
                continue
            if char.y0 > y1 + NEIGHBOUR_GAP or char.y1 < y0 - NEIGHBOUR_GAP:
                continue
            new_x0, new_x1 = min(x0, char.x0), max(x1, char.x1)
            if on_own_baseline and (new_x0 < x0 or new_x1 > x1):
                continue  # no creeping sideways into the next expression
            new_y0, new_y1 = min(y0, char.y0), max(y1, char.y1)
            if (new_y1 - new_y0) - origin_height > max_growth:
                continue
            kept.add(id(char))
            if (new_x0, new_y0, new_x1, new_y1) == (x0, y0, x1, y1):
                continue
            x0, y0, x1, y1 = new_x0, new_y0, new_x1, new_y1
            changed = True
        for rect in rules:
            if rect[0] > x1 + 2 or rect[2] < x0 - 2:
                continue
            if rect[1] > y1 + NEIGHBOUR_GAP or rect[3] < y0 - NEIGHBOUR_GAP:
                continue
            candidate = (min(x0, rect[0]), min(y0, rect[1]), max(x1, rect[2]), max(y1, rect[3]))
            if candidate == (x0, y0, x1, y1):
                continue
            if (candidate[3] - candidate[1]) - origin_height > max_growth:
                continue
            x0, y0, x1, y1 = candidate
            changed = True
        if not changed:
            break
    box = _clamp_hard(page, (x0, y0, x1, y1), own_baselines)
    return box, _foreign_ink(page, box, kept, own_baselines)


def _foreign_ink(page: Page, box, kept: set[int],
                 baselines: list[float]) -> list[tuple[float, float, float, float]]:
    """Boxes of ink that fall inside the crop but belong to something else.

    An inline fraction reaches into the vertical band of the line below it, so a rectangle
    holding the whole fraction unavoidably catches a slice of the next line. Rather than
    clipping the fraction, that foreign ink is painted out when the crop is rendered.

    The rule is deliberately timid, because painting out a glyph of the expression itself
    would be far worse than leaving a stray one in: only prose is removed, plus mathematics
    that sits on a line of prose well away from the expression's own baselines."""
    x0, y0, x1, y1 = box
    foreign: list[tuple[float, float, float, float]] = []
    for line in page.lines:
        prose_line = _has_prose_word(line)
        for char in line.chars:
            if char.is_space or id(char) in kept:
                continue
            if char.x1 <= x0 or char.x0 >= x1 or char.y1 <= y0 or char.y0 >= y1:
                continue
            mathematical = (char.role in (Role.MATH_VAR, Role.MATH_UP)
                            or char.c in DOT_GLYPHS)
            if mathematical and baselines:
                # Everything the box grew along is already in `kept`, so a mathematics glyph
                # that is neither kept nor near one of this expression's own baselines
                # belongs to a different expression: the fraction on the line above, for one.
                if min(abs(char.oy - base) for base in baselines) <= NEAR_BASELINE:
                    continue
            foreign.append(_ink_box(char))
    return foreign


NEAR_BASELINE = 6.0
ASCENT_SHARE = 0.78
DESCENT_SHARE = 0.24


def _ink_box(char) -> tuple[float, float, float, float]:
    """The extractor reports each character's full em box, which for 10 pt text is about
    14.5 pt tall and reaches well into the neighbouring lines. Painting that box out would
    erase the limits of a summation sitting between the lines, so the band actually covered
    by ink is used instead."""
    top = max(char.y0, char.oy - ASCENT_SHARE * char.size)
    bottom = min(char.y1, char.oy + DESCENT_SHARE * char.size)
    return (char.x0 - 0.15, top, char.x1 + 0.15, bottom)


SLOT_MARGIN = 3.0
HARD_SLOT = 30.0


def _clamp_hard(page: Page, bbox, baselines: list[float]):
    """A last guard against runaway growth: never reach more than 30 pt beyond the outermost
    baseline of the expression itself."""
    if not baselines:
        return bbox
    x0, y0, x1, y1 = bbox
    return (x0, max(y0, min(baselines) - HARD_SLOT), x1, min(y1, max(baselines) + HARD_SLOT))


def _clamp_to_slot(page: Page, bbox, baselines: list[float]):
    """Keep a box inside the vertical slot of its own line: never let it reach across the
    baseline of the paragraph line above or below."""
    if not baselines:
        return bbox
    top_baseline, bottom_baseline = min(baselines), max(baselines)
    # Clamp to the ink of the neighbouring paragraph lines, not their baselines, so that no
    # sliver of the next line's ascenders is left in the picture.
    above = [line.y1 for line in page.lines
             if line.zone == Zone.MAIN and _has_prose_word(line)
             and line.baseline < top_baseline - SLOT_MARGIN]
    below = [line.y0 for line in page.lines
             if line.zone == Zone.MAIN and _has_prose_word(line)
             and line.baseline > bottom_baseline + SLOT_MARGIN]
    x0, y0, x1, y1 = bbox
    if above:
        y0 = max(y0, max(above) + 0.5)
    if below:
        y1 = min(y1, min(below) - 0.5)
    if y1 - y0 < 6:
        return bbox
    return (x0, y0, x1, y1)


def inline_math_bbox(page: Page, host, run_chars, rules):
    """Box an inline expression from the pieces that are known to belong to it.

    Growing a box along whatever mathematics it touches cannot tell this expression's
    numerator from the one on the line above, and inline fractions on consecutive lines do
    overlap. The fragments were already matched to their host line when the page was
    classified, so that assignment is used instead of proximity."""
    x0 = min(c.x0 for c in run_chars)
    x1 = max(c.x1 for c in run_chars)
    kept = {id(char) for char in run_chars}
    boxes = [(x0, min(c.y0 for c in run_chars), x1, max(c.y1 for c in run_chars))]

    # Two expressions on one line share their fragment lines, so the fragments are filtered
    # glyph by glyph rather than line by line.
    for fragment in page.auxiliary.get(id(host), ()):
        for char in fragment.chars:
            if char.is_space or char.x1 < x0 - 3 or char.x0 > x1 + 3:
                continue
            boxes.append((char.x0, char.y0, char.x1, char.y1))
            kept.add(id(char))

    for rect in rules:
        if rect[3] - rect[1] > 2.0 or rect[2] - rect[0] > 160:
            continue
        if rect[2] < x0 - 3 or rect[0] > x1 + 3:
            continue
        if abs(rect[1] - host.baseline) > 12.0:
            continue
        boxes.append(rect)

    bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))
    return bbox, _foreign_ink(page, bbox, kept, [host.baseline])
