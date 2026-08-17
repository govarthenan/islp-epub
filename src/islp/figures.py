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

from .pagemodel import Page, Zone

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
    caption_tops = sorted(line.y0 for line, _, _ in captions)

    for line, kind, number in captions:
        caption_top = line.y0
        # the region cannot reach above the previous caption on this page
        floor = TOP_MARGIN
        for other_top in caption_tops:
            if other_top < caption_top - 4:
                floor = max(floor, other_top)

        # a body-text line above the caption ends the region
        for other in page.lines:
            if other is line or other.zone != Zone.MAIN:
                continue
            if other.y1 <= caption_top - 2 and other.y1 > floor:
                if other.x0 <= 102.5 and other.x1 - other.x0 > 200 and other.size >= 9.5:
                    floor = max(floor, other.y1)

        band = (floor + 1.0, caption_top - 1.0)
        if band[1] - band[0] < 8:
            continue

        pieces: list[tuple[float, float, float, float]] = []
        for rect in page.drawing_rects + page.image_rects:
            if rect[1] >= band[0] - 3 and rect[3] <= band[1] + 3 and rect[0] >= CONTENT_X0:
                if rect[2] - rect[0] > 0.2 and rect[3] - rect[1] > 0.2:
                    pieces.append(rect)
        for other in page.lines:
            if other is line:
                continue
            if other.zone in (Zone.HEADER, Zone.FOOTER):
                continue
            if other.y0 >= band[0] - 3 and other.y1 <= band[1] + 3:
                pieces.append(other.bbox)
        for box in ruled:
            if box[1] >= band[0] - 6 and box[3] <= band[1] + 6:
                pieces.append(box)

        bbox = _union(pieces)
        if bbox is None:
            continue
        bbox = (
            max(CONTENT_X0, bbox[0] - 4),
            max(band[0] - 2, bbox[1] - 4),
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
        if line.zone != Zone.MAIN:
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
