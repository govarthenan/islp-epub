"""Turn a PDF page into a list of visual lines, each tagged with the zone it belongs to.

Geometry of the book (measured, see journal entries 002 and 004):
  page box            0 .. 504.567 x 0 .. 720 pt
  running head        y < 50
  main text column    x 91.0 .. 413.8
  Jupyter prompt      x 53 .. 89, colour #0068b4, font LMMonoLt10-Bold
  right margin note   x >= 416, colour #595959, font LMRoman8
  page-bottom folio   y > 650 (front matter only)

Colours carry meaning:
  #000000 prose      #984100 code      #0068b4 prompt or lab sub-heading
  #595959 margin note
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import pymupdf

from .fonts import Role, classify, family

MAIN_X0 = 88.0
MAIN_X1 = 415.0
MARGIN_X0 = 415.5
HEADER_Y = 50.0
FOOTER_Y = 648.0
PROMPT_X1 = 90.0
COLUMN_GAP = 200.0        # body pages: effectively no limit
INDEX_COLUMN_GAP = 28.0   # the index is set in two columns that share baselines
INDEX_GUTTER_X = 252.0    # nothing crosses the gutter between those two columns

COLOUR_PROSE = 0x000000
COLOUR_CODE = 0x984100
COLOUR_ACCENT = 0x0068B4
COLOUR_MARGIN = 0x595959

# Ligatures are kept as single glyphs so that each glyph keeps one honest pen position;
# they are expanded to plain letters later, when the text is written out.
TEXT_FLAGS = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
              | pymupdf.TEXT_PRESERVE_LIGATURES)


class Zone(str, Enum):
    HEADER = "header"
    FOOTNOTE = "footnote"
    FOOTER = "footer"
    MARGIN = "margin"
    PROMPT = "prompt"
    CODE = "code"
    GRAPHIC = "graphic"
    MAIN = "main"


@dataclass
class Char:
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    ox: float  # origin x (pen position)
    oy: float  # origin y (baseline)
    font: str
    size: float
    colour: int
    role: Role
    link: str = ""

    @property
    def is_space(self) -> bool:
        return not self.c.strip()


@dataclass
class VLine:
    """A visual line: everything printed on one baseline, left to right."""

    chars: list[Char]
    zone: Zone = Zone.MAIN
    baseline: float = 0.0
    size: float = 10.0
    page: int = 0
    cell_fill: str | None = None  # "input" | "output" for code lines

    @property
    def x0(self) -> float:
        return min(c.x0 for c in self.chars)

    @property
    def x1(self) -> float:
        return max(c.x1 for c in self.chars)

    @property
    def y0(self) -> float:
        return min(c.y0 for c in self.chars)

    @property
    def y1(self) -> float:
        return max(c.y1 for c in self.chars)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def text(self) -> str:
        return "".join(c.c for c in self.chars)

    def dominant_role(self) -> Role:
        counts: dict[Role, int] = {}
        for char in self.chars:
            if char.is_space:
                continue
            counts[char.role] = counts.get(char.role, 0) + 1
        if not counts:
            return Role.OTHER
        return max(counts, key=lambda role: counts[role])

    def role_fraction(self, role: Role) -> float:
        total = sum(1 for c in self.chars if not c.is_space)
        if not total:
            return 0.0
        return sum(1 for c in self.chars if not c.is_space and c.role == role) / total


@dataclass
class CodeCell:
    """A shaded rectangle behind a Jupyter input or output cell."""

    kind: str  # "input" | "output"
    rect: tuple[float, float, float, float]


@dataclass
class Page:
    index: int  # zero-based PDF page index
    width: float
    height: float
    lines: list[VLine]
    code_cells: list[CodeCell] = field(default_factory=list)
    header_text: str = ""
    drawing_rects: list[tuple[float, float, float, float]] = field(default_factory=list)
    image_rects: list[tuple[float, float, float, float]] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    rotated_rects: list[tuple[float, float, float, float]] = field(default_factory=list)
    # host line id -> the numerator, denominator and limit fragments that belong to it
    auxiliary: dict = field(default_factory=dict)


def _span_text(span: dict) -> str:
    """Raw dict spans carry 'chars'; plain dict spans carry 'text'."""
    if "text" in span:
        return span["text"]
    return "".join(char["c"] for char in span.get("chars", ()))


def _line_baseline(line: dict) -> tuple[float, float]:
    """Dominant baseline and size of a raw dict line: the largest font size wins, ties
    broken by character count. Sub/superscripts are smaller so they never win."""
    best: tuple[float, int, float, float] | None = None
    for span in line["spans"]:
        text = _span_text(span)
        if not text.strip():
            continue
        key = (round(span["size"], 1), len(text))
        if best is None or key > (best[0], best[1]):
            best = (key[0], key[1], span["origin"][1], span["size"])
    if best is None:
        span = line["spans"][0]
        return span["origin"][1], span["size"]
    return best[2], best[3]


def _collect_code_cells(page: pymupdf.Page) -> list[CodeCell]:
    cells: list[CodeCell] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        rect = drawing["rect"]
        if fill is None or rect.width < 150 or rect.height < 4:
            continue
        red, green, blue = (round(component, 2) for component in fill[:3])
        if (red, green, blue) == (1.0, 0.96, 0.9):
            kind = "input"
        elif (red, green, blue) == (1.0, 1.0, 1.0):
            kind = "output"
        else:
            continue
        cells.append(CodeCell(kind, (rect.x0, rect.y0, rect.x1, rect.y1)))
    return _merge_cells(cells)


def _merge_cells(cells: list[CodeCell]) -> list[CodeCell]:
    """Cells are drawn one strip per line; merge vertically touching strips of one kind."""
    cells = sorted(cells, key=lambda c: (c.rect[1], c.rect[0]))
    merged: list[CodeCell] = []
    for cell in cells:
        if merged and merged[-1].kind == cell.kind and cell.rect[1] - merged[-1].rect[3] < 3.0:
            previous = merged[-1]
            previous.rect = (
                min(previous.rect[0], cell.rect[0]),
                min(previous.rect[1], cell.rect[1]),
                max(previous.rect[2], cell.rect[2]),
                max(previous.rect[3], cell.rect[3]),
            )
        else:
            merged.append(CodeCell(cell.kind, cell.rect))
    return merged


def footnote_rule_y(page: pymupdf.Page) -> float | None:
    """LaTeX draws a short rule above the footnotes. Everything under it on the page is a
    note, not body text."""
    best = None
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if drawing["type"] != "s" or rect.height > 1.2:
            continue
        if not (40 <= rect.width <= 130) or not (88 <= rect.x0 <= 94):
            continue
        if rect.y0 < 380:
            continue
        best = rect.y0 if best is None else max(best, rect.y0)
    return best


def _zone_for(line: VLine, page_height: float, footnote_y: float | None = None) -> Zone:
    x0, y0, x1, y1 = line.bbox
    if y1 < HEADER_Y:
        return Zone.HEADER
    if y0 > FOOTER_Y:
        return Zone.FOOTER
    if line.dominant_role() == Role.GRAPHIC:
        return Zone.GRAPHIC
    # Margin notes are set at 8 pt. The index runs wider than the text column at full size,
    # so width alone is not enough to tell them apart.
    if x0 >= MARGIN_X0 and line.size <= 8.6:
        return Zone.MARGIN
    if footnote_y is not None and y0 > footnote_y and line.size < 9.0:
        return Zone.FOOTNOTE
    return Zone.MAIN


EQUATION_NUMBER_X = 378.0
EQUATION_NUMBER_RE = re.compile(r"^\(\d+\.\d+\)$")


def _split_equation_number(line: VLine) -> tuple[VLine, VLine | None]:
    """An equation number shares its baseline with the equation, so the extractor glues the
    two together. Left joined, the number dilutes the line's mathematics and stretches it to
    the full column width, and the line then reads as prose."""
    tail = [c for c in line.chars if c.x0 >= EQUATION_NUMBER_X]
    if not tail or len(tail) == len(line.chars):
        return line, None
    if not EQUATION_NUMBER_RE.match("".join(c.c for c in tail).strip()):
        return line, None
    body = [c for c in line.chars if c.x0 < EQUATION_NUMBER_X]
    if not body:
        return line, None
    return (VLine(body, line.zone, line.baseline, line.size, line.page, line.cell_fill),
            VLine(tail, line.zone, line.baseline, line.size, line.page, line.cell_fill))


def _split_margin(line: VLine) -> tuple[VLine, VLine | None]:
    """The extractor glues right-margin notes onto main text lines. Split them apart."""
    def is_margin(char: Char) -> bool:
        return (char.x0 >= MARGIN_X0 and char.size <= 8.6) or char.colour == COLOUR_MARGIN

    main_chars = [c for c in line.chars if not is_margin(c)]
    margin_chars = [c for c in line.chars if is_margin(c)]
    if not margin_chars or not main_chars:
        return line, None
    main = VLine(main_chars, line.zone, line.baseline, line.size, line.page)
    margin = VLine(margin_chars, Zone.MARGIN, line.baseline, line.size, line.page)
    return main, margin


def _collect_links(page: pymupdf.Page) -> list[dict]:
    """Internal cross-references, as target keys the document assembler can resolve later.
    PyMuPDF already reports the destination point in top-left page coordinates."""
    links = []
    for link in page.get_links():
        rect = link.get("from")
        if rect is None:
            continue
        if link.get("kind") == pymupdf.LINK_GOTO and link.get("to") is not None:
            links.append({"rect": tuple(rect),
                          "target": f"{link['page']}:{link['to'].y:.0f}"})
        elif link.get("kind") == pymupdf.LINK_URI and link.get("uri"):
            links.append({"rect": tuple(rect), "uri": link["uri"]})
    return links


def _tag_links(chars: list[Char], links: list[dict]) -> None:
    for char in chars:
        if char.is_space:
            continue
        centre_x = (char.x0 + char.x1) / 2
        for link in links:
            lx0, ly0, lx1, ly1 = link["rect"]
            if lx0 <= centre_x <= lx1 and ly0 - 1 <= char.oy <= ly1 + 1:
                char.link = link.get("target") or ("uri:" + link["uri"])
                break


def load_page(doc: pymupdf.Document, index: int, two_column: bool = False) -> Page:
    page = doc[index]
    raw = page.get_text("rawdict", flags=TEXT_FLAGS)
    links = _collect_links(page)

    groups: list[tuple[float, float, list[Char]]] = []  # (baseline, size, chars)
    image_rects: list[tuple[float, float, float, float]] = []
    rotated_rects: list[tuple[float, float, float, float]] = []

    for block in raw["blocks"]:
        if block["type"] != 0:
            image_rects.append(tuple(block["bbox"]))
            continue
        for line in block["lines"]:
            if abs(line["dir"][0] - 1.0) > 0.01:
                # Turned text: a few table headers are set sideways. It is not part of the
                # reading flow, but its box must be inside the region that gets rendered.
                rotated_rects.append(tuple(line["bbox"]))
                continue
            baseline, size = _line_baseline(line)
            chars: list[Char] = []
            for span in line["spans"]:
                role = classify(span["font"])
                for char in span["chars"]:
                    bbox = char["bbox"]
                    chars.append(
                        Char(
                            c=char["c"],
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            ox=char["origin"][0],
                            oy=char["origin"][1],
                            font=span["font"],
                            size=span["size"],
                            colour=span["color"],
                            role=role,
                        )
                    )
            if chars:
                if links:
                    _tag_links(chars, links)
                groups.append((baseline, size, chars))

    # Merge groups that share a baseline (code cells and prompts arrive as separate blocks).
    groups.sort(key=lambda g: (round(g[0], 1), min(c.x0 for c in g[2])))
    # Pieces on one baseline belong to one visual line only if they are also close
    # horizontally. The index needs that guard, because its two columns share baselines and
    # would otherwise be read as single interleaved lines. Body pages must not have it: the
    # columns of a printed regression summary are far apart and do belong to one line.
    gap_limit = INDEX_COLUMN_GAP if two_column else COLUMN_GAP
    merged: list[tuple[float, float, list[Char]]] = []
    for baseline, size, chars in groups:
        start = min(c.x0 for c in chars)
        joins = (merged
                 and abs(merged[-1][0] - baseline) <= 1.5
                 and abs(merged[-1][1] - size) < 0.6
                 and start - max(c.x1 for c in merged[-1][2]) < gap_limit)
        if joins and two_column:
            previous_start = min(c.x0 for c in merged[-1][2])
            joins = (previous_start >= INDEX_GUTTER_X) == (start >= INDEX_GUTTER_X)
        if joins:
            merged[-1][2].extend(chars)
        else:
            merged.append((baseline, size, list(chars)))

    code_cells = _collect_code_cells(page)
    footnote_y = footnote_rule_y(page)

    lines: list[VLine] = []
    for baseline, size, chars in merged:
        chars.sort(key=lambda c: c.ox)
        line = VLine(chars=chars, baseline=baseline, size=size, page=index)
        line.zone = _zone_for(line, page.rect.height, footnote_y)
        if line.zone == Zone.MAIN:
            line, margin = _split_margin(line)
            line.zone = _zone_for(line, page.rect.height, footnote_y)
            if margin is not None:
                lines.append(margin)
            line, number = _split_equation_number(line)
            if number is not None:
                lines.append(number)
        # Jupyter prompt plus code content live on one baseline; tag the whole line as code.
        if line.zone == Zone.MAIN and line.role_fraction(Role.MONO) > 0.6:
            for cell in code_cells:
                if cell.rect[1] - 2 <= line.baseline <= cell.rect[3] + 4:
                    line.zone = Zone.CODE
                    line.cell_fill = cell.kind
                    break
            else:
                # A cell's output sometimes overflows its shaded rectangle. A line that is
                # almost entirely typewriter is code wherever it sits.
                if line.x0 < PROMPT_X1 or line.role_fraction(Role.MONO) > 0.85:
                    line.zone = Zone.CODE
                    line.cell_fill = "output"
        lines.append(line)

    lines.sort(key=lambda ln: (round(ln.baseline, 1), ln.x0))

    header_text = " ".join(ln.text.strip() for ln in lines if ln.zone == Zone.HEADER).strip()
    drawing_rects = [
        (d["rect"].x0, d["rect"].y0, d["rect"].x1, d["rect"].y1)
        for d in page.get_drawings()
    ]

    return Page(
        index=index,
        width=page.rect.width,
        height=page.rect.height,
        lines=lines,
        code_cells=code_cells,
        header_text=header_text,
        drawing_rects=drawing_rects,
        image_rects=image_rects,
        links=links,
        rotated_rects=rotated_rects,
    )
