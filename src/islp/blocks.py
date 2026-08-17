"""Group visual lines into semantic blocks: headings, paragraphs, display equations,
code cells, captions and list items.

The classifier leans on measurements rather than guesses:

  * prose lines carry at least one two-letter word in a Latin Modern text font;
  * display equations are indented past the paragraph margin (x >= 94.5) and carry no
    prose word, or contain a CMEX glyph (a large operator or delimiter);
  * a new paragraph is announced by the 9.9 pt first-line indent (x 91.0 -> 100.9);
  * figure and table captions open with "FIGURE n.n." or "TABLE n.n.";
  * code lives in shaded cells, cream for input and white for output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .fonts import Role, is_extension_font
from .pagemodel import Char, Page, VLine, Zone

PROSE_LEFT = 91.0
PARA_INDENT = 100.9
DISPLAY_MIN_X = 94.5
CHAPTER_TITLE_SIZE = 20.7
SECTION_SIZE = 14.3
SUBSECTION_SIZE = 12.0
COLOUR_ACCENT = 0x0068B4

CAPTION_RE = re.compile(r"^\s*(FIGURE|TABLE)\s+([A-Z]?\.?\d+\.\d+)\.")
EQNUM_RE = re.compile(r"^\s*\((\d+\.\d+)\)\s*$")
LIST_MARKER_RE = re.compile(r"^\s*(\(?[a-z]\)|\(?[ivx]+\)|\d+\.)\s")
PROSE_WORD_RE = re.compile(r"[A-Za-zÀ-ɏ]{2,}")


class Kind(str, Enum):
    CHAPTER_NUMBER = "chapter_number"
    CHAPTER_TITLE = "chapter_title"
    SECTION = "section"
    SUBSECTION = "subsection"
    LAB_HEADING = "lab_heading"
    CAPTION = "caption"
    PROSE = "prose"
    DISPLAY = "display"
    EQNUM = "eqnum"
    CODE = "code"
    MARGIN = "margin"
    FOOTNOTE = "footnote"
    OTHER = "other"


@dataclass
class TaggedLine:
    line: VLine
    kind: Kind
    is_new_paragraph: bool = False
    list_marker: str = ""
    group: list[VLine] = field(default_factory=list)


@dataclass
class Block:
    kind: str
    page: int
    lines: list[VLine] = field(default_factory=list)
    text: str = ""
    html: str = ""
    number: str = ""
    level: int = 0
    eq_number: str = ""
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    code_kind: str = ""
    list_marker: str = ""
    meta: dict = field(default_factory=dict)


def _prose_text(line: VLine) -> str:
    return "".join(c.c for c in line.chars if c.role in (Role.PROSE, Role.PROSE_ITALIC, Role.PROSE_BOLD))


def has_prose_word(line: VLine) -> bool:
    return bool(PROSE_WORD_RE.search(_prose_text(line)))


def math_fraction(line: VLine) -> float:
    solid = [c for c in line.chars if not c.is_space]
    if not solid:
        return 0.0
    return sum(1 for c in solid if c.role in (Role.MATH_VAR, Role.MATH_UP)) / len(solid)


def _all_dots(line: VLine) -> bool:
    solid = [c for c in line.chars if not c.is_space]
    return bool(solid) and all(c.c in ".·…⋮⋱⋯" for c in solid)


def _has_extension(line: VLine) -> bool:
    return any(is_extension_font(c.font) or c.c == "�" for c in line.chars)


def classify_line(line: VLine) -> Kind:
    if line.zone == Zone.MARGIN:
        return Kind.MARGIN
    if line.zone == Zone.CODE:
        return Kind.CODE
    if line.zone == Zone.FOOTNOTE:
        return Kind.FOOTNOTE
    if line.zone in (Zone.HEADER, Zone.FOOTER, Zone.GRAPHIC):
        return Kind.OTHER

    text = line.text.strip()
    if not text:
        return Kind.OTHER

    if EQNUM_RE.match(text) and line.x0 > 380:
        return Kind.EQNUM
    if CAPTION_RE.match(text):
        return Kind.CAPTION

    size = line.size
    if size >= CHAPTER_TITLE_SIZE - 1.0:
        return Kind.CHAPTER_NUMBER if len(text) <= 3 else Kind.CHAPTER_TITLE
    if abs(size - SECTION_SIZE) < 0.6:
        return Kind.SECTION
    if abs(size - SUBSECTION_SIZE) < 0.6:
        return Kind.SUBSECTION

    solid = [c for c in line.chars if not c.is_space]
    if solid and all(c.colour == COLOUR_ACCENT for c in solid) and line.x0 < 95 and len(text) < 70:
        return Kind.LAB_HEADING

    # A display equation is set away from both paragraph margins and is nearly all
    # mathematics. Small words inside one ("and", "if", "otherwise") are allowed, which is why
    # the test is a proportion rather than the absence of prose.
    indented_past_margins = (line.x0 >= DISPLAY_MIN_X
                             and abs(line.x0 - PARA_INDENT) > 1.6)
    if indented_past_margins and not LIST_MARKER_RE.match(text):
        share = math_fraction(line)
        if share > 0.6 or _all_dots(line) or (_has_extension(line) and share > 0.35):
            return Kind.DISPLAY
    return Kind.PROSE


AUXILIARY_BASELINE_GAP = 10.0
FULL_WIDTH = 200.0


def _covers_math(host: VLine, fragment: VLine, rules) -> bool:
    """Whether the fragment sits over mathematics belonging to the host line.

    A fraction leaves nothing on the host's own baseline except its rule, so the numerator and
    denominator sit over a drawn line rather than over a character. The rule counts."""
    for char in host.chars:
        if char.role not in (Role.MATH_VAR, Role.MATH_UP):
            continue
        if char.x0 <= fragment.x1 + 1 and char.x1 >= fragment.x0 - 1:
            return True
    for x0, y0, x1, y1 in rules:
        if y1 - y0 > 2.0 or x1 - x0 > 160:
            continue
        if abs(y0 - host.baseline) > 9.0:
            continue
        if x0 <= fragment.x1 + 1 and x1 >= fragment.x0 - 1:
            return True
    return False


def _drop_auxiliary_math_lines(tagged: list[TaggedLine], rules,
                               auxiliary: dict | None = None) -> None:
    """A fraction or a large operator set inside a paragraph puts its numerator, denominator
    and limits on baselines of their own. Those fragments look exactly like little display
    equations, so they are matched back to the paragraph line they belong to and dropped: the
    cropped image of that line's mathematics already contains them."""
    # A fragment belongs to a paragraph line only if that line actually carries mathematics.
    # Without that test the opening brace of a piecewise definition, which happens to sit
    # close to the paragraph above it, was being thrown away.
    # A host is a line of body text, recognised by starting at one of the two paragraph
    # margins. Requiring it to be wide as well missed the last line of a paragraph, which is
    # short by definition, and left the denominators of its inline fractions stranded as
    # equations of their own.
    hosts = [entry.line for entry in tagged
             if entry.kind == Kind.PROSE
             and (abs(entry.line.x0 - PROSE_LEFT) < 1.6 or abs(entry.line.x0 - PARA_INDENT) < 1.6)
             and any(char.role in (Role.MATH_VAR, Role.MATH_UP) for char in entry.line.chars)]
    ordered = sorted(tagged, key=lambda item: item.line.baseline)
    for position, entry in enumerate(ordered):
        if entry.kind != Kind.DISPLAY:
            continue
        for host in hosts:
            if abs(host.baseline - entry.line.baseline) >= AUXILIARY_BASELINE_GAP:
                continue
            if not (host.x0 - 2 <= entry.line.x0 and entry.line.x1 <= host.x1 + 2):
                continue
            # It belongs to that line only if it sits over the line's own mathematics. The
            # opening brace of a display construct happens to sit close to the paragraph
            # above it, but not above any of that paragraph's symbols.
            if _covers_math(host, entry.line, rules):
                entry.kind = Kind.OTHER
                if auxiliary is not None:
                    auxiliary.setdefault(id(host), []).append(entry.line)
                break


def tag_lines(page: Page) -> list[TaggedLine]:
    tagged: list[TaggedLine] = []
    previous_prose: VLine | None = None
    for line in page.lines:
        kind = classify_line(line)
        entry = TaggedLine(line=line, kind=kind)
        if kind == Kind.PROSE:
            marker = LIST_MARKER_RE.match(line.text)
            indent_start = abs(line.x0 - PARA_INDENT) < 1.6
            if marker and line.x0 > PROSE_LEFT + 2:
                entry.list_marker = marker.group(1)
                entry.is_new_paragraph = True
            elif indent_start:
                entry.is_new_paragraph = True
            previous_prose = line
        tagged.append(entry)
    page.auxiliary = {}
    _drop_auxiliary_math_lines(tagged, page.drawing_rects, page.auxiliary)
    return tagged


def _bbox_union(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


DISPLAY_GAP = 24.0
MARGIN_NOTE_GAP = 16.0


EQUATION_BODY_MAX_X = 402.0


EQUATION_ARM_MAX_WIDTH = 260.0
EQUATION_ARM_GAP = 16.0


def _inside_equation(line: VLine, run: list[VLine]) -> bool:
    """True when a line of words belongs to the equation rather than to the paragraph.

    The arms of a piecewise definition ("1 if stroke;") mix a couple of mathematical symbols
    with ordinary words, so they read as prose to the classifier. Two things separate them
    from a paragraph line that merely happens to be indented: they carry mathematics, and
    they are short and set in from both paragraph margins."""
    if not any(char.role in (Role.MATH_VAR, Role.MATH_UP) for char in line.chars):
        return False
    return (line.x0 >= DISPLAY_MIN_X
            and abs(line.x0 - PARA_INDENT) > 1.6
            and line.x1 <= EQUATION_BODY_MAX_X
            and line.x1 - line.x0 <= EQUATION_ARM_MAX_WIDTH)


def _detach_equation_number(lines: list[VLine]) -> str:
    """An equation number typeset on the same baseline as the equation is merged into it by
    the extractor. Split it back off so it does not land inside the cropped image."""
    for line in lines:
        tail = [c for c in line.chars if c.x0 >= 378.0]
        if not tail:
            continue
        text = "".join(c.c for c in tail).strip()
        match = EQNUM_RE.match(text)
        if match and len(tail) < len(line.chars):
            line.chars = [c for c in line.chars if c.x0 < 378.0]
            return match.group(1)
    return ""


def _group_margin_notes(tagged: list[TaggedLine], page: Page) -> list[TaggedLine]:
    """Margin notes are interleaved with body lines once everything is sorted by baseline, so
    the lines of one note are rarely adjacent. Group them by vertical proximity instead."""
    notes = [entry for entry in tagged if entry.kind == Kind.MARGIN]
    others = [entry for entry in tagged if entry.kind != Kind.MARGIN]
    notes.sort(key=lambda entry: entry.line.baseline)
    grouped: list[TaggedLine] = []
    for entry in notes:
        if len(entry.line.text.strip()) < 2:
            continue  # stray single glyphs are not notes
        if grouped and entry.line.baseline - grouped[-1].group[-1].baseline < MARGIN_NOTE_GAP:
            grouped[-1].group.append(entry.line)
        else:
            grouped.append(TaggedLine(line=entry.line, kind=Kind.MARGIN, group=[entry.line]))
    merged = others + grouped
    merged.sort(key=lambda entry: (round(entry.line.baseline, 1), entry.line.x0))
    return merged


def assemble(page: Page) -> list[Block]:
    """Turn one page into blocks, in reading order."""
    tagged = _group_margin_notes(tag_lines(page), page)
    blocks: list[Block] = []
    index = 0

    def push(block: Block) -> None:
        if block.lines:
            block.bbox = _bbox_union([ln.bbox for ln in block.lines])
        blocks.append(block)

    def finish() -> list[Block]:
        return _merge_overlapping_displays(blocks)

    while index < len(tagged):
        entry = tagged[index]
        kind = entry.kind

        if kind in (Kind.OTHER,):
            index += 1
            continue

        if kind == Kind.MARGIN:
            push(Block(kind="margin", page=page.index, lines=entry.group or [entry.line]))
            index += 1
            continue

        if kind == Kind.EQNUM:
            # attach to the display block that is vertically nearest
            number = EQNUM_RE.match(entry.line.text.strip()).group(1)
            target = None
            for block in reversed(blocks):
                if block.kind == "display" and abs(block.bbox[3] - entry.line.y1) < 30:
                    target = block
                    break
            if target is not None:
                target.eq_number = number
            else:
                push(Block(kind="eqnum_orphan", page=page.index, lines=[entry.line], eq_number=number))
            index += 1
            continue

        if kind == Kind.CODE:
            run = [entry.line]
            code_kind = entry.line.cell_fill or "output"
            index += 1
            side_notes: list[VLine] = []
            while index < len(tagged):
                following = tagged[index]
                if following.kind == Kind.MARGIN:
                    side_notes.append(following.line)
                    index += 1
                    continue
                if following.kind != Kind.CODE:
                    break
                if (following.line.cell_fill or "output") != code_kind:
                    break
                if following.line.baseline - run[-1].baseline > 18:
                    break
                run.append(following.line)
                index += 1
            push(Block(kind="code", page=page.index, lines=run, code_kind=code_kind))
            for note in side_notes:
                push(Block(kind="margin", page=page.index, lines=[note]))
            continue

        if kind == Kind.DISPLAY:
            run = [entry.line]
            eq_number = ""
            side_notes: list[VLine] = []
            index += 1
            while index < len(tagged):
                following = tagged[index]
                if following.line.baseline - run[-1].baseline > DISPLAY_GAP:
                    break
                if following.kind == Kind.DISPLAY:
                    run.append(following.line)
                    index += 1
                    continue
                if following.kind == Kind.EQNUM:
                    # The number sits on a baseline of its own, often between the numerator
                    # and the denominator of the equation it labels. Absorbing it instead of
                    # stopping there keeps the equation in one piece.
                    eq_number = EQNUM_RE.match(following.line.text.strip()).group(1)
                    index += 1
                    continue
                if following.kind == Kind.MARGIN:
                    side_notes.append(following.line)
                    index += 1
                    continue
                if (following.kind == Kind.PROSE
                        and following.line.baseline - run[-1].baseline <= EQUATION_ARM_GAP
                        and _inside_equation(following.line, run)):
                    # The "if ..." arms of a piecewise definition are ordinary words set
                    # inside the equation. They belong to it.
                    run.append(following.line)
                    index += 1
                    continue
                break
            block = Block(kind="display", page=page.index, lines=run)
            block.eq_number = eq_number or _detach_equation_number(run)
            push(block)
            for note in side_notes:
                push(Block(kind="margin", page=page.index, lines=[note]))
            continue

        if kind == Kind.FOOTNOTE:
            run = [entry.line]
            index += 1
            while index < len(tagged) and tagged[index].kind == Kind.FOOTNOTE:
                candidate = tagged[index].line
                # a new note starts with its own raised number
                solid = [c for c in candidate.chars if not c.is_space]
                starts_note = bool(solid) and solid[0].size < candidate.size * 0.92 \
                    and solid[0].c.isdigit()
                if starts_note:
                    break
                run.append(candidate)
                index += 1
            push(Block(kind="footnote", page=page.index, lines=run))
            continue

        if kind == Kind.CAPTION:
            run = [entry.line]
            index += 1
            while index < len(tagged) and tagged[index].kind == Kind.PROSE and \
                    abs(tagged[index].line.size - run[-1].size) < 0.6 and \
                    tagged[index].line.baseline - run[-1].baseline < 16 and \
                    not tagged[index].is_new_paragraph:
                run.append(tagged[index].line)
                index += 1
            match = CAPTION_RE.match(run[0].text.strip())
            push(Block(kind="caption", page=page.index, lines=run,
                       meta={"caption_type": match.group(1).lower()}, number=match.group(2)))
            continue

        if kind in (Kind.CHAPTER_NUMBER, Kind.CHAPTER_TITLE, Kind.SECTION, Kind.SUBSECTION,
                    Kind.LAB_HEADING):
            run = [entry.line]
            index += 1
            while index < len(tagged) and tagged[index].kind == kind and \
                    tagged[index].line.baseline - run[-1].baseline < 26:
                run.append(tagged[index].line)
                index += 1
            level = {
                Kind.CHAPTER_TITLE: 1,
                Kind.SECTION: 2,
                Kind.SUBSECTION: 3,
                Kind.LAB_HEADING: 4,
                Kind.CHAPTER_NUMBER: 0,
            }[kind]
            push(Block(kind="heading", page=page.index, lines=run, level=level,
                       meta={"heading_kind": kind.value}))
            continue

        # prose: gather until the next new paragraph or a different kind
        run = [entry.line]
        marker = entry.list_marker
        index += 1
        while index < len(tagged):
            following = tagged[index]
            if following.kind == Kind.MARGIN:
                blocks.append(Block(kind="margin", page=page.index,
                                    lines=following.group or [following.line]))
                index += 1
                continue
            if following.kind != Kind.PROSE or following.is_new_paragraph:
                break
            if following.line.baseline - run[-1].baseline > 26:
                break
            run.append(following.line)
            index += 1
        push(Block(kind="para", page=page.index, lines=run, list_marker=marker))

    return finish()


VERTICAL_TOUCH = 2.0
HORIZONTAL_SHARE = 0.3


def _merge_overlapping_displays(blocks: list[Block]) -> list[Block]:
    """Two display blocks never overlap on the page unless they are halves of one equation.

    A `cases` block whose first arm is separated from the rest by an intervening baseline can
    still come out as two blocks; where their boxes overlap, they are the same equation and
    are put back together."""
    merged: list[Block] = []
    for block in blocks:
        if block.kind != "display":
            merged.append(block)
            continue
        target = None
        for candidate in merged:
            if candidate.kind != "display":
                continue
            if _boxes_overlap(candidate.bbox, block.bbox):
                target = candidate
                break
        if target is None:
            merged.append(block)
            continue
        target.lines = sorted(target.lines + block.lines, key=lambda ln: (ln.baseline, ln.x0))
        target.bbox = _bbox_union([ln.bbox for ln in target.lines])
        target.eq_number = target.eq_number or block.eq_number
    return merged


def _boxes_overlap(first, second) -> bool:
    vertical = min(first[3], second[3]) - max(first[1], second[1])
    if vertical <= VERTICAL_TOUCH:
        return False
    horizontal = min(first[2], second[2]) - max(first[0], second[0])
    narrower = min(first[2] - first[0], second[2] - second[0])
    return narrower > 0 and horizontal / narrower > HORIZONTAL_SHARE
