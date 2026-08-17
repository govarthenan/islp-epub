"""Assemble the whole book: pages -> blocks -> chapters, with paragraphs stitched across
page breaks, hyphenation undone, and every piece of mathematics registered for rendering.

Hyphenation is resolved from the book's own vocabulary. A line ending in "-" is joined
without the hyphen when the joined form occurs elsewhere in the book more often than the
hyphenated form does, which keeps "non-linear" intact while repairing "individ-ual".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .blocks import assemble
from .fonts import Role
from .figures import inline_math_bbox
from .inline import Tier, build_inline
from .pagemodel import Page, VLine, Zone, load_page
from .symbols import fix_unicode

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")
TRAILING_HYPHEN_RE = re.compile(r"[-‐]((?:</[a-z]+>)*)$")
MATH_PLACEHOLDER_RE = re.compile("\x00MATH(\\d+)\x00")


@dataclass
class MathItem:
    ident: str
    tier: str
    latex: str
    page: int
    bbox: tuple[float, float, float, float]
    raw_text: str
    reason: str
    display: bool
    key: str
    meta_guess: str = ""
    foreign_ink: list = field(default_factory=list)
    eq_number: str = ""
    context: str = ""
    chapter: str = ""
    occurrences: int = 1


@dataclass
class MathRegistry:
    items: dict[str, MathItem] = field(default_factory=dict)
    by_key: dict[str, str] = field(default_factory=dict)
    counter: int = 0
    text_runs: int = 0  # solved as plain HTML: no image, no model call

    def add(
        self,
        *,
        tier: str,
        latex: str,
        page: int,
        bbox,
        raw_text: str,
        reason: str,
        display: bool,
        key: str,
        eq_number: str = "",
        context: str = "",
        chapter: str = "",
    ) -> str:
        if not display and key in self.by_key:
            ident = self.by_key[key]
            self.items[ident].occurrences += 1
            return ident
        self.counter += 1
        ident = f"m{self.counter:05d}"
        self.items[ident] = MathItem(
            ident=ident,
            tier=tier,
            latex=latex,
            page=page,
            bbox=tuple(bbox),
            raw_text=raw_text,
            reason=reason,
            display=display,
            key=key,
            eq_number=eq_number,
            context=context,
            chapter=chapter,
        )
        if not display:
            self.by_key[key] = ident
        return ident


@dataclass
class DocBlock:
    kind: str
    html: str = ""
    page: int = 0
    level: int = 0
    number: str = ""
    eq_number: str = ""
    math_id: str = ""
    code_kind: str = ""
    list_marker: str = ""
    anchor: str = ""
    caption_type: str = ""
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    meta: dict = field(default_factory=dict)


@dataclass
class Chapter:
    ident: str
    title: str
    number: str
    start_page: int
    blocks: list[DocBlock] = field(default_factory=list)


@dataclass
class Document:
    chapters: list[Chapter] = field(default_factory=list)
    math: MathRegistry = field(default_factory=MathRegistry)
    toc: list = field(default_factory=list)


# ------------------------------------------------------------------------------------------
# hyphenation
# ------------------------------------------------------------------------------------------


def build_vocabulary(pages: list[Page]) -> Counter[str]:
    vocabulary: Counter[str] = Counter()
    for page in pages:
        for line in page.lines:
            if line.zone != Zone.MAIN:
                continue
            text = "".join(c.c for c in line.chars if c.role in (Role.PROSE, Role.PROSE_ITALIC, Role.PROSE_BOLD))
            words = WORD_RE.findall(text)
            if text.rstrip().endswith("-") and words:
                words = words[:-1]  # the last word is broken across the line
            for word in words:
                vocabulary[word.lower()] += 1
    return vocabulary


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def join_lines(html_parts: list[str], vocabulary: Counter[str]) -> str:
    """Join line fragments into a paragraph, undoing LaTeX hyphenation where the book's own
    usage says the word is not really hyphenated."""
    out = ""
    for part in html_parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
            continue
        plain = _strip_tags(out)
        # A page-number range broken over two lines ("347-" / "350") must close up.
        if plain.rstrip().endswith(("–", "—")) and _strip_tags(part)[:1].isdigit():
            out = out + part
            continue
        if TRAILING_HYPHEN_RE.search(out) and plain.rstrip().endswith(("-", "‐")):
            head_match = re.search(r"([A-Za-z]+)[-‐]$", plain.rstrip())
            tail_match = re.match(r"([A-Za-z]+)", _strip_tags(part))
            if head_match and tail_match:
                head, tail = head_match.group(1).lower(), tail_match.group(1).lower()
                joined = vocabulary.get(head + tail, 0)
                hyphenated = vocabulary.get(head + "-" + tail, 0)
                if joined >= hyphenated:
                    out = TRAILING_HYPHEN_RE.sub(r"\1", out) + part
                    continue
            else:
                out = TRAILING_HYPHEN_RE.sub(r"\1", out) + part
                continue
        out = out + " " + part
    return re.sub(r"\s{2,}", " ", out).strip()


# ------------------------------------------------------------------------------------------
# code reconstruction
# ------------------------------------------------------------------------------------------

PROMPT_FONT = "LMMONOLT"


def _is_prompt(char) -> bool:
    """The Jupyter prompt is set in its own font, LMMonoLt10-Bold. Splitting on the font is
    exact; splitting on an x threshold is not, because a content character can start a
    hundredth of a point to the left of it."""
    return char.font.split("+")[-1].upper().startswith(PROMPT_FONT)


def code_block_text(lines: list[VLine]) -> str:
    """Rebuild a code cell as plain text.

    The Jupyter prompt ("In [64]:") is printed in the left margin in its own, narrower font,
    so it is handled as a literal prefix. Inside the cell, space characters are kept as they
    come from the PDF and positional gaps add further padding, which is what preserves the
    alignment of printed array output."""
    content_chars = [c for line in lines for c in line.chars if not _is_prompt(c)]
    if not content_chars:
        content_chars = [c for line in lines for c in line.chars]
    if not content_chars:
        return ""

    deltas: list[float] = []
    for line in lines:
        ordered = sorted((c for c in line.chars if not _is_prompt(c)), key=lambda c: c.ox)
        for left, right in zip(ordered, ordered[1:], strict=False):
            gap = right.ox - left.ox
            if 2.0 < gap < 9.0:
                deltas.append(gap)
    deltas.sort()
    advance = deltas[len(deltas) // 2] if deltas else 4.74
    origin = min(c.ox for c in content_chars)

    prompts = [
        "".join(c.c for c in sorted((ch for ch in line.chars if _is_prompt(ch)), key=lambda ch: ch.ox)).strip()
        for line in lines
    ]
    prompt_width = max((len(p) for p in prompts if p), default=0)
    prompt_width = prompt_width + 1 if prompt_width else 0

    rendered: list[str] = []
    for line, prompt in zip(lines, prompts, strict=True):
        ordered = sorted((c for c in line.chars if not _is_prompt(c)), key=lambda c: c.ox)
        while ordered and ordered[0].is_space:
            ordered.pop(0)  # the gap after the prompt is already in prompt_width
        buffer = (prompt + " ").ljust(prompt_width) if prompt else " " * prompt_width
        previous = None
        for char in ordered:
            char_text = fix_unicode(char.c)
            if previous is None:
                buffer += " " * max(0, round((char.ox - origin) / advance))
            elif char.x0 - previous.x1 > 0.35 * advance:
                buffer += " " * max(0, round((char.ox - previous.ox) / advance) - 1)
            buffer += char_text
            previous = char
        if buffer.strip():
            rendered.append(buffer.rstrip())
    return "\n".join(rendered)


# ------------------------------------------------------------------------------------------
# document assembly
# ------------------------------------------------------------------------------------------


def _inline_math_boxes(page: Page, blocks, rules) -> list:
    """Boxes of the inline expressions on this page that will be rendered as images."""
    boxes = []
    for block in blocks:
        if block.kind != "para":
            continue
        for line in block.lines:
            for run in build_inline(line.chars, rules).math_runs:
                if run.tier != Tier.VLM:
                    continue
                box, _ = inline_math_bbox(page, line, run.chars, rules)
                boxes.append(box)
    return boxes


def _resolve_duplicate_math(page: Page, blocks, rules):
    """Drop a display block that an inline expression already covers.

    An equation set with words in it ("minimize ... subject to ...") reads as a paragraph,
    and the paragraph's inline images then hold the whole equation. Any display block that
    was made from the same pixels would print it a second time."""
    from .figures import inline_math_bbox  # noqa: F401  (imported for clarity)

    display_blocks = [block for block in blocks if block.kind == "display"]
    if not display_blocks:
        return blocks
    inline_boxes = _inline_math_boxes(page, blocks, rules)
    if not inline_boxes:
        return blocks
    redundant = {
        id(block)
        for block in display_blocks
        if any(_overlap_share(block.bbox, box) > DUPLICATE_COVER for box in inline_boxes)
    }
    return [block for block in blocks if id(block) not in redundant]


def _line_html(
    line: VLine,
    rules,
    registry: MathRegistry,
    chapter: str,
    context: str,
    page: Page | None = None,
    display_boxes: list | None = None,
) -> tuple[str, list[str]]:
    from .figures import inline_math_bbox

    result = build_inline(line.chars, rules)
    registry.text_runs += result.text_runs
    ids: list[str] = []
    for run in result.math_runs:
        bbox = run.bbox
        foreign: list = []
        if run.tier.value == "vlm" and page is not None:
            bbox, foreign = inline_math_bbox(page, line, run.chars, rules)
            if display_boxes and any(_overlap_share(bbox, box) > 0.5 for box in display_boxes):
                # This run is part of a display equation that is already being rendered whole
                # a few lines further down. Rendering it here as well would print the equation
                # twice.
                ids.append("")
                continue
        ident = registry.add(
            tier=run.tier.value,
            latex=run.latex,
            page=line.page,
            bbox=bbox,
            raw_text=run.raw_text,
            reason=run.reason,
            display=False,
            key=run.key,
            context=context,
            chapter=chapter,
        )
        registry.items[ident].foreign_ink = foreign
        ids.append(ident)
    def substitute(match: re.Match) -> str:
        ident = ids[int(match.group(1))]
        return "{{MATH:" + ident + "}}" if ident else ""

    html = MATH_PLACEHOLDER_RE.sub(substitute, result.html)
    return html, ids


def _slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return text or "section"


FRONT_SKIP = {0, 1, 4, 5, 6, 7, 8, 9, 10}  # cover, dedication, and the printed table of contents
INDEX_START = 602  # zero-based: the Index runs to the end of the book


@dataclass
class Section:
    """A heading that the navigation document should point at."""

    level: int
    title: str
    anchor: str
    chapter_ident: str


def _chapter_spans(toc: list) -> list[tuple[int, int, str, str]]:
    """(start_page0, end_page0_exclusive, number, title) for every level-1 entry."""
    level_one = [(page - 1, title) for level, title, page in toc if level == 1]
    spans = []
    for position, (start, title) in enumerate(level_one):
        end = level_one[position + 1][0] if position + 1 < len(level_one) else 10**9
        match = re.match(r"^(\d+)\s+(.*)$", title)
        number, name = (match.group(1), match.group(2)) if match else ("", title)
        spans.append((start, end, number, name))
    return spans


INLINE_TAGS = "em|strong|code|i|b|sub|sup"


def _sanitize(html: str) -> str:
    """Normalise whitespace and pull stray spaces out of inline tags."""
    html = html.replace("­", "")
    html = re.sub(r"\s+", " ", html)
    for _ in range(3):
        html = re.sub(rf"(\s+)(</(?:{INLINE_TAGS})>)", r"\2\1", html)
        html = re.sub(rf"(<(?:{INLINE_TAGS})>)(\s+)", r"\2\1", html)
    html = re.sub(rf"<({INLINE_TAGS})>\s*</\1>", " ", html)
    for tag in ("em", "strong", "code", "i"):
        html = re.sub(rf"</{tag}>(\s*)<{tag}>", r"\1", html)
    return re.sub(r"\s{2,}", " ", html).strip()


def _strip_emphasis(html: str) -> str:
    return re.sub(r"</?(?:em|strong)>", "", html)


DISPLAY_MAX_GROWTH = 12.0
DUPLICATE_OVERLAP = 0.6
DUPLICATE_COVER = 0.4


def _overlap_share(first, second) -> float:
    """Intersection over the smaller of two boxes."""
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    areas = [(box[2] - box[0]) * (box[3] - box[1]) for box in (first, second)]
    smallest = min(areas)
    return intersection / smallest if smallest else 0.0


COLUMN_SPLIT_X = 250.0
SUB_ENTRY_INDENT = 14.0
CONTINUATION_INDENT = 32.0


def index_blocks(page: Page, rules, registry: MathRegistry, chapter_ident: str, vocabulary) -> list[DocBlock]:
    """The index is set in two columns, so reading it in baseline order interleaves them.
    Read the left column top to bottom, then the right, and rebuild each entry from its own
    hanging indent."""
    lines = [line for line in page.lines if line.zone == Zone.MAIN and line.text.strip()]
    if not lines:
        return []
    columns: dict[int, list[VLine]] = {0: [], 1: []}
    for line in lines:
        columns[0 if line.x0 < COLUMN_SPLIT_X else 1].append(line)

    blocks: list[DocBlock] = []
    for column in (0, 1):
        entries = sorted(columns[column], key=lambda ln: ln.baseline)
        if not entries:
            continue
        origin = min(line.x0 for line in entries)
        current: list[VLine] = []
        level = 0

        def flush(run: list[VLine], depth: int) -> None:
            if not run:
                return
            parts = [_line_html(line, rules, registry, chapter_ident, "", page)[0] for line in run]
            html = _sanitize(join_lines(parts, vocabulary))
            if html:
                blocks.append(
                    DocBlock(
                        kind="index-entry",
                        html=html,
                        page=page.index,
                        level=depth,
                        bbox=run[0].bbox,
                        meta={"y0": run[0].y0},
                    )
                )

        for line in entries:
            offset = line.x0 - origin
            if offset < SUB_ENTRY_INDENT:
                flush(current, level)
                current, level = [line], 0
            elif offset < CONTINUATION_INDENT:
                flush(current, level)
                current, level = [line], 1
            else:
                current.append(line)
        flush(current, level)
    return blocks


def assemble_document(pdf_path: Path, progress: bool = False, first: int = 0, last: int | None = None) -> Document:
    from .figures import consume_lines, detect_regions

    pdf = pymupdf.open(pdf_path)
    toc = pdf.get_toc()
    spans = _chapter_spans(toc)

    pages: list[Page] = []
    regions_by_page: dict[int, list] = {}
    stop = pdf.page_count if last is None else min(last, pdf.page_count)
    for index in range(first, stop):
        if index in FRONT_SKIP:
            continue
        page = load_page(pdf, index, two_column=index >= INDEX_START)
        regions = detect_regions(page, pdf[index])
        consume_lines(page, regions)
        regions_by_page[index] = regions
        pages.append(page)
        if progress and index % 50 == 0:
            print(f"  page {index + 1}/{pdf.page_count}", flush=True)

    vocabulary = build_vocabulary(pages)
    document = Document(toc=toc)
    registry = document.math

    chapters: dict[int, Chapter] = {}
    for position, (start, _end, number, title) in enumerate(spans):
        ident = f"ch{position:02d}"
        chapters[start] = Chapter(ident=ident, title=title, number=number, start_page=start)

    def chapter_for(page_index: int) -> Chapter:
        chosen = None
        for start, _end, _number, _title in spans:
            if page_index >= start:
                chosen = chapters[start]
        return chosen or next(iter(chapters.values()))

    front = Chapter(ident="front", title="Dedication", number="", start_page=1)
    document.chapters.append(front)

    used: list[Chapter] = []
    seen_idents: set[str] = set()
    page_display_boxes: list[tuple[float, float, float, float]] = []
    pending_margins: list[str] = []
    last_para: DocBlock | None = None
    previous_context = ""

    for page in pages:
        chapter = chapter_for(page.index)
        if page.index >= INDEX_START:
            chapter = chapters[spans[-1][0]]
        if chapter.ident not in seen_idents:
            seen_idents.add(chapter.ident)
            used.append(chapter)
            last_para = None

        rules = page.drawing_rects
        page_display_boxes = []
        if page.index >= INDEX_START:
            chapter.blocks.extend(index_blocks(page, rules, registry, chapter.ident, vocabulary))
            last_para = None
            continue

        regions = regions_by_page.get(page.index, [])
        blocks = assemble(page)
        blocks = _resolve_duplicate_math(page, blocks, rules)
        display_boxes = [block.bbox for block in blocks if block.kind == "display"]
        region_by_number = {(r.kind, r.number): r for r in regions}

        for block in blocks:
            if block.kind == "margin":
                parts = [
                    _line_html(line, rules, registry, chapter.ident, previous_context, page, display_boxes)[0] for line in block.lines
                ]
                pending_margins.append(_sanitize(join_lines(parts, vocabulary)))
                continue

            if block.kind == "heading":
                parts = [_line_html(line, rules, registry, chapter.ident, "", page, display_boxes)[0] for line in block.lines]
                text = _sanitize(" ".join(parts))
                if block.meta.get("heading_kind") == "chapter_number":
                    continue
                heading = DocBlock(
                    kind="heading",
                    html=_strip_emphasis(text),
                    page=page.index,
                    level=block.level,
                    anchor="",
                    bbox=block.bbox,
                    meta={"y0": block.bbox[1]},
                )
                chapter.blocks.append(heading)
                last_para = None
                continue

            if block.kind == "code":
                code_text = code_block_text(block.lines)
                if re.sub(r"(?m)^\s*(In|Out)\s*\[\d+\]:\s*$", "", code_text).strip():
                    chapter.blocks.append(
                        DocBlock(
                            kind="code",
                            html=code_text,
                            page=page.index,
                            code_kind=block.code_kind,
                            bbox=block.bbox,
                            meta={"y0": block.bbox[1]},
                        )
                    )
                last_para = None
                continue

            if block.kind == "display":
                raw = "\n".join(line.text for line in block.lines)
                guesses = []
                complete = True
                for line in block.lines:
                    result = build_inline(line.chars, rules)
                    if any(run.tier != Tier.TEXT for run in result.math_runs):
                        complete = False
                    guesses.append(_strip_tags(result.html))
                from .figures import expand_math_bbox

                display_chars = [char for ln in block.lines for char in ln.chars]
                # A display block already spans its own numerator, rule and denominator, so
                # it needs almost no growing. A generous cap here lets one equation reach
                # into the next.
                display_bbox, display_foreign = expand_math_bbox(
                    page, block.bbox, [ln.baseline for ln in block.lines], display_chars, max_growth=DISPLAY_MAX_GROWTH
                )
                if any(_overlap_share(display_bbox, seen) > DUPLICATE_OVERLAP for seen in page_display_boxes):
                    # Two fragments of one equation that both grew back into the same
                    # rectangle. Rendering it twice would be worse than dropping one.
                    continue
                page_display_boxes.append(display_bbox)
                ident = registry.add(
                    tier="display",
                    latex="",
                    page=page.index,
                    bbox=display_bbox,
                    raw_text=raw,
                    reason="display-equation",
                    display=True,
                    key=f"disp-{page.index}-{round(block.bbox[1])}",
                    eq_number=block.eq_number,
                    context=previous_context[-600:],
                    chapter=chapter.ident,
                )
                registry.items[ident].meta_guess = "\n".join(guesses) if complete else ""
                registry.items[ident].foreign_ink = display_foreign
                chapter.blocks.append(
                    DocBlock(
                        kind="display",
                        math_id=ident,
                        page=page.index,
                        eq_number=block.eq_number,
                        bbox=display_bbox,
                        meta={"y0": block.bbox[1]},
                    )
                )
                last_para = None
                continue

            if block.kind == "footnote":
                parts = [_line_html(line, rules, registry, chapter.ident, "", page, display_boxes)[0] for line in block.lines]
                html = _sanitize(join_lines(parts, vocabulary))
                if html:
                    chapter.blocks.append(
                        DocBlock(
                            kind="footnote", html=html, page=page.index, bbox=block.bbox, meta={"y0": block.bbox[1]}
                        )
                    )
                continue

            if block.kind == "caption":
                parts = [_line_html(line, rules, registry, chapter.ident, "", page, display_boxes)[0] for line in block.lines]
                text = _sanitize(" ".join(parts))
                caption_type = block.meta.get("caption_type", "figure")
                region = region_by_number.get((caption_type, block.number))
                media = DocBlock(
                    kind=caption_type,
                    page=page.index,
                    number=block.number,
                    html=text,
                    caption_type=caption_type,
                    bbox=region.bbox if region else (0, 0, 0, 0),
                    meta={"y0": (region.bbox[1] if region else block.bbox[1])},
                )
                chapter.blocks.append(media)
                last_para = None
                continue

            if block.kind == "para":
                parts = []
                for line in block.lines:
                    fragment, _ = _line_html(line, rules, registry, chapter.ident, previous_context, page, display_boxes)
                    parts.append(fragment)
                html = _sanitize(join_lines(parts, vocabulary))
                if block.list_marker:
                    html = re.sub(r"^\s*" + re.escape(block.list_marker) + r"\s*", "", html, count=1)
                if not html:
                    continue
                first = block.lines[0]
                indented = abs(first.x0 - PARA_INDENT_X) < 1.6
                marker = block.list_marker
                if (
                    not indented
                    and not marker
                    and last_para is not None
                    and last_para.kind == "para"
                    and not last_para.list_marker
                    and chapter.blocks
                    and chapter.blocks[-1] is last_para
                ):
                    last_para.html = join_lines([last_para.html, html], vocabulary)
                else:
                    body_lines = block.lines[1:] if len(block.lines) > 1 else block.lines
                    left = min(line.x0 for line in body_lines)
                    doc_block = DocBlock(
                        kind="para",
                        html=html,
                        page=page.index,
                        list_marker=marker,
                        meta={"left": round(left, 1), "indented": indented, "y0": block.bbox[1]},
                    )
                    chapter.blocks.append(doc_block)
                    last_para = doc_block
                previous_context = _strip_tags(html)
                if pending_margins and last_para is not None:
                    notes = last_para.meta.setdefault("margin_notes", [])
                    notes.extend(pending_margins)
                    pending_margins = []
                continue

    document.chapters = [front] + used
    return document


PARA_INDENT_X = 100.9
