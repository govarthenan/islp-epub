"""Build the EPUB from the PDF.

    uv run python src/build_epub.py [--limit N] [--no-figures]

Stages:
  1. assemble the document model from the PDF
  2. render figures and tables to 300 ppi grayscale PNG
  3. render mathematics: LaTeX to SVG where LaTeX is known, cropped PNG otherwise
  4. write XHTML and package the EPUB
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))

from islp.document import Document, assemble_document
from islp.epub import EpubBuilder, NavPoint, _escape
from islp.figures import render_region

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "ISLP_website.pdf"
WORK = ROOT / "work"
OUTPUT = ROOT / "output"

FIGURE_DPI = 300
MATH_DPI = 400
GREY_LEVELS = 16
BODY_POINT_SIZE = 10.0  # the book's body size; used to convert PDF points to em

MATH_TOKEN_RE = re.compile(r"\{\{MATH:(m\d+)\}\}")
LINK_ANCHOR_RE = re.compile(r'<a href="\{\{LINK:(\d+):(-?\d+)\}\}">(.*?)</a>', re.S)

TITLE = "An Introduction to Statistical Learning with Applications in Python"
AUTHORS = ["Gareth James", "Daniela Witten", "Trevor Hastie", "Robert Tibshirani",
           "Jonathan Taylor"]


# ---------------------------------------------------------------------------------------
# image helpers
# ---------------------------------------------------------------------------------------

def pixmap_to_png(pix: pymupdf.Pixmap, levels: int = GREY_LEVELS) -> bytes:
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if levels and levels < 256:
        image = image.quantize(colors=levels, method=Image.MEDIANCUT)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def render_crop(pdf_page: pymupdf.Page, bbox, dpi: int, pad: float = 1.0,
                foreign_ink: list | None = None) -> bytes:
    box = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    pix = render_region(pdf_page, box, dpi=dpi)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if foreign_ink:
        scale = dpi / 72.0
        painter = ImageDraw.Draw(image)
        for fx0, fy0, fx1, fy1 in foreign_ink:
            painter.rectangle(
                [((fx0 - box[0]) * scale, (fy0 - box[1]) * scale),
                 ((fx1 - box[0]) * scale, (fy1 - box[1]) * scale)],
                fill=255,
            )
    quantised = image.quantize(colors=GREY_LEVELS, method=Image.MEDIANCUT)
    buffer = io.BytesIO()
    quantised.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


# ---------------------------------------------------------------------------------------
# mathematics
# ---------------------------------------------------------------------------------------

def load_verified_latex() -> dict[str, str]:
    path = WORK / "math_latex.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {ident: entry["latex"] for ident, entry in data.items() if entry.get("latex")}


def render_svgs(jobs: list[dict]) -> dict[str, dict]:
    if not jobs:
        return {}
    jobs_path = WORK / "math_jobs.json"
    out_dir = WORK / "math_svg"
    manifest_path = WORK / "math_svg_manifest.json"
    jobs_path.write_text(json.dumps(jobs))
    subprocess.run(
        ["node", str(ROOT / "src" / "render_math.cjs"), str(jobs_path), str(out_dir),
         str(manifest_path)],
        check=True, cwd=ROOT,
    )
    payload = json.loads(manifest_path.read_text())
    if payload["failures"]:
        (WORK / "math_svg_failures.json").write_text(json.dumps(payload["failures"], indent=1))
    return payload["manifest"]


# ---------------------------------------------------------------------------------------
# XHTML rendering
# ---------------------------------------------------------------------------------------

class Renderer:
    def __init__(self, document: Document, svg_manifest: dict, math_images: dict,
                 figure_images: dict, targets: dict | None = None) -> None:
        self.document = document
        self.svg_manifest = svg_manifest
        self.math_images = math_images
        self.figure_images = figure_images
        self.targets = targets or {}
        self.unresolved = 0
        self.resolved = 0

    def resolve_link(self, page: int, y: float) -> str:
        """Point a cross-reference at the nearest block on the destination page."""
        entries = self.targets.get(page)
        if not entries:
            self.unresolved += 1
            return ""
        for y0, y1, href in entries:
            if y0 - 8 <= y <= y1 + 8:
                self.resolved += 1
                return href
        following = [entry for entry in entries if entry[0] >= y - 8]
        chosen = following[0] if following else entries[-1]
        self.resolved += 1
        return chosen[2]

    def expand_links(self, html: str) -> str:
        """Resolve a cross-reference, or drop the anchor entirely when its destination is not
        in this build: a dead link is worse than plain text."""
        def replace(match: re.Match) -> str:
            href = self.resolve_link(int(match.group(1)), float(match.group(2)))
            text = match.group(3)
            return f'<a href="{href}">{text}</a>' if href else text
        return LINK_ANCHOR_RE.sub(replace, html)

    def inline_math(self, ident: str) -> str:
        item = self.document.math.items[ident]
        entry = self.svg_manifest.get(ident)
        if entry:
            height = entry["heightEm"] or 1.0
            valign = entry["valignEm"] or 0.0
            alt = _escape(entry["tex"])
            return (f'<img class="mi" src="../math/{entry["file"]}" alt="{alt}" '
                    f'style="height:{height:.3f}em;vertical-align:{valign:.3f}em"/>')
        name = self.math_images.get(ident)
        if name:
            x0, y0, x1, y1 = item.bbox
            width = (x1 - x0) / BODY_POINT_SIZE
            height = (y1 - y0) / BODY_POINT_SIZE
            alt = _escape(item.raw_text.strip() or "mathematical expression")
            return (f'<img class="mi" src="../images/{name}" alt="{alt}" '
                    f'style="width:{width:.3f}em;height:{height:.3f}em"/>')
        return _escape(item.raw_text)

    def expand(self, html: str) -> str:
        html = MATH_TOKEN_RE.sub(lambda m: self.inline_math(m.group(1)), html)
        return self.expand_links(html)

    def display_math(self, ident: str, eq_number: str) -> str:
        item = self.document.math.items[ident]
        entry = self.svg_manifest.get(ident)
        if entry:
            width = entry["widthEm"] or 1.0
            alt = _escape(entry["tex"])
            body = (f'<img src="../math/{entry["file"]}" alt="{alt}" '
                    f'style="width:{width:.3f}em"/>')
        else:
            name = self.math_images.get(ident)
            if not name:
                return f'<div class="eq">{_escape(item.raw_text)}</div>'
            x0, y0, x1, y1 = item.bbox
            width = (x1 - x0) / BODY_POINT_SIZE
            alt = _escape(item.raw_text.strip().replace("\n", " ") or "display equation")
            body = f'<img src="../images/{name}" alt="{alt}" style="width:{width:.3f}em"/>'
        number = f'<span class="eqno">({_escape(eq_number)})</span>' if eq_number else ""
        anchor = f' id="eq{eq_number.replace(".", "-")}"' if eq_number else ""
        return f'<div class="eq"{anchor}>{body}{number}</div>'


def paragraph_class(block) -> str:
    """Indent level comes from the printed page: the left margin of the body lines gives the
    list depth, and the 9.9 pt first-line indent says whether a paragraph is a fresh one."""
    left = block.meta.get("left", 91.0)
    level = 0
    if left >= 125:
        level = 2
    elif left >= 96:
        level = 1
    if block.list_marker:
        return {0: "noindent", 1: "li", 2: "li2"}[level]
    if block.meta.get("indented", False):
        return {0: "", 1: "li-cont-in", 2: "li2-cont-in"}[level]
    return {0: "noindent", 1: "li-cont", 2: "li2-cont"}[level]


def render_chapter(chapter, renderer: Renderer, nav_children: list[NavPoint],
                   href_base: str) -> str:
    parts: list[str] = []
    heading_counter = [0]
    title_written = False

    for block in chapter.blocks:
        anchor_id = block.anchor or ""
        extra_anchor = f'<span id="{anchor_id}"></span>' if anchor_id else ""
        if block.kind == "heading":
            heading_counter[0] += 1
            anchor = block.anchor or f"h{heading_counter[0]}"
            text = renderer.expand(block.html)
            if block.level <= 1 and not title_written:
                title_written = True
                number = f'<span class="chapnum">Chapter {_escape(chapter.number)}</span>' \
                    if chapter.number else ""
                parts.append(f'<h1 id="{anchor}">{number}{text}</h1>')
            else:
                level = min(max(block.level, 2), 5)
                parts.append(f'<h{level} id="{anchor}">{text}</h{level}>')
                if block.level in (2, 3):
                    nav_children.append(
                        NavPoint(title=re.sub(r"<[^>]+>", "", text), level=block.level,
                                 href=f"{href_base}#{anchor}")
                    )
            continue

        if block.kind == "para":
            css = paragraph_class(block)
            marker = (f'<span class="marker">{_escape(block.list_marker)}</span> '
                      if block.list_marker else "")
            attribute = f' class="{css}"' if css else ""
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f"<p{attribute}{ident}>{marker}{renderer.expand(block.html)}</p>")
            notes = [renderer.expand(note) for note in block.meta.get("margin_notes", [])]
            if notes:
                # The printed book scatters these terms down the outer margin. A 7 inch page
                # has no margin to spare, so they collapse into one quiet line.
                joined = " &#183; ".join(notes)
                parts.append(f'<p class="marginnote">{joined}</p>')
            continue

        if block.kind == "display":
            parts.append(extra_anchor + renderer.display_math(block.math_id, block.eq_number))
            continue

        if block.kind == "code":
            css = "input" if block.code_kind == "input" else "output"
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f'<div class="codeblock"{ident}><pre class="{css}">'
                         f"{_escape(block.html)}</pre></div>")
            continue

        if block.kind in ("figure", "table"):
            name = renderer.figure_images.get((block.page, block.kind, block.number))
            caption = renderer.expand(block.html)
            caption = re.sub(r"^(<strong>)(FIGURE|TABLE)([^<]*)(</strong>)",
                             r'<span class="label">\2\3</span>', caption, count=1)
            image = (f'<img src="../images/{name}" alt="{block.kind} {_escape(block.number)}"/>'
                     if name else "")
            named = f'{block.kind[0]}{block.number.replace(".", "-")}'
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f'<div class="figure"{ident}><span id="{named}"></span>{image}'
                         f'<p class="caption">{caption}</p></div>')
            continue

        if block.kind == "footnote":
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f'<aside class="footnote" epub:type="footnote"{ident}>'
                         f"{renderer.expand(block.html)}</aside>")
            continue

        if block.kind == "index-entry":
            css = "index-entry" if block.level == 0 else "index-sub"
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f'<p class="{css}"{ident}>{renderer.expand(block.html)}</p>')
            continue

    return "\n".join(parts)


# ---------------------------------------------------------------------------------------
# front matter
# ---------------------------------------------------------------------------------------

def dedication_html(pdf: pymupdf.Document) -> str:
    lines = [line.strip() for line in pdf[1].get_text().splitlines() if line.strip()]
    return "\n".join(f'<p class="dedication">{_escape(line)}</p>' for line in lines)


# ---------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="stop after this PDF page")
    parser.add_argument("--out", default="ISLP.epub")
    args = parser.parse_args()

    WORK.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    print("1/4 assembling document model ...", flush=True)
    document = assemble_document(PDF, progress=True, last=args.limit)

    pdf = pymupdf.open(PDF)
    builder = EpubBuilder(identifier="urn:uuid:islp-python-1st-edition-reflow",
                          title=TITLE)
    builder.authors = AUTHORS
    builder.publisher = "Springer"
    builder.source = "ISLP_website.pdf (statlearning.com), first printing July 5 2023"
    builder.rights = ("Converted from the freely distributed PDF for personal, educational "
                      "and non-commercial use only. All rights remain with the authors and "
                      "publisher.")
    builder.description = ("A reflowable conversion of the ISLP textbook, prepared for "
                           "reading on a 7 inch e-ink screen.")

    # --- cover -------------------------------------------------------------------------
    print("2/4 rendering figures and tables ...", flush=True)
    cover = pixmap_to_png(pdf[0].get_pixmap(dpi=170, colorspace=pymupdf.csGRAY, alpha=False),
                          levels=16)
    builder.add_resource("images/cover.png", "image/png", cover, "cover-image", "cover-image")
    builder.set_cover("cover-image")
    builder.add_document("cover.xhtml", "Cover",
                         '<div class="cover"><img src="../images/cover.png" alt="Cover"/></div>',
                         "cover")
    builder.nav.append(NavPoint("Cover", "text/cover.xhtml", 1))

    builder.add_document("dedication.xhtml", "Dedication", dedication_html(pdf), "dedication")
    builder.nav.append(NavPoint("Dedication", "text/dedication.xhtml", 1))

    # --- figures -----------------------------------------------------------------------
    figure_images: dict[tuple, str] = {}
    for chapter in document.chapters:
        for block in chapter.blocks:
            if block.kind not in ("figure", "table"):
                continue
            if block.bbox == (0, 0, 0, 0):
                continue
            name = f"{block.kind}-{block.number.replace('.', '-')}-p{block.page + 1}.png"
            data = render_crop(pdf[block.page], block.bbox, FIGURE_DPI, pad=2.0)
            builder.add_resource(f"images/{name}", "image/png", data,
                                 f"img-{name.replace('.', '-')}")
            figure_images[(block.page, block.kind, block.number)] = name
    print(f"    {len(figure_images)} figures and tables", flush=True)

    # --- mathematics -------------------------------------------------------------------
    print("3/4 rendering mathematics ...", flush=True)
    verified = load_verified_latex()
    jobs: list[dict] = []
    for ident, item in document.math.items.items():
        latex = verified.get(ident) or (item.latex if item.tier == "latex" else "")
        if latex:
            jobs.append({"id": ident, "tex": latex, "display": item.display})
    svg_manifest = render_svgs(jobs)
    for ident, entry in svg_manifest.items():
        data = (WORK / "math_svg" / entry["file"]).read_bytes()
        builder.add_resource(f"math/{entry['file']}", "image/svg+xml", data, f"svg-{ident}")

    math_images: dict[str, str] = {}
    for ident, item in document.math.items.items():
        if ident in svg_manifest:
            continue
        if item.tier == "text":
            continue
        name = f"{ident}.png"
        data = render_crop(pdf[item.page], item.bbox, MATH_DPI, pad=0.8)
        builder.add_resource(f"images/{name}", "image/png", data, f"img-{ident}")
        math_images[ident] = name
    print(f"    {len(svg_manifest)} equations as SVG, {len(math_images)} as cropped images",
          flush=True)

    # --- cross-reference targets ---------------------------------------------------------
    # Every block gets an anchor, so any of the book's 4,000 internal references can land on
    # the nearest thing to the point the PDF pointed at.
    targets: dict[int, list[tuple[float, float, str]]] = {}
    for chapter in document.chapters:
        if not chapter.blocks:
            continue
        for position, block in enumerate(chapter.blocks):
            block.anchor = f"b{position}"
            y0 = block.meta.get("y0", block.bbox[1] if block.bbox != (0, 0, 0, 0) else 0.0)
            y1 = block.bbox[3] if block.bbox != (0, 0, 0, 0) else y0 + 12
            targets.setdefault(block.page, []).append(
                (float(y0), float(max(y1, y0 + 4)), f"{chapter.ident}.xhtml#{block.anchor}"))
    for entries in targets.values():
        entries.sort()

    # --- chapters ----------------------------------------------------------------------
    print("4/4 writing XHTML ...", flush=True)
    renderer = Renderer(document, svg_manifest, math_images, figure_images, targets)
    for index, chapter in enumerate(document.chapters):
        if not chapter.blocks:
            continue
        name = f"{chapter.ident}.xhtml"
        href = f"text/{name}"
        children: list[NavPoint] = []
        body = render_chapter(chapter, renderer, children, href)
        label = (f"{chapter.number}. {chapter.title}" if chapter.number else chapter.title)
        builder.add_document(name, label, body, chapter.ident)
        if not builder.bodymatter_href:
            builder.bodymatter_href = href
        point = NavPoint(label, href, 1)
        for child in children:
            if child.level == 2 or not point.children:
                point.children.append(child)
            else:
                point.children[-1].children.append(child)
        builder.nav.append(point)

    target = OUTPUT / args.out
    builder.write(target)
    size = target.stat().st_size

    tiers: dict[str, int] = {}
    occurrences: dict[str, int] = {}
    for item in document.math.items.values():
        tiers[item.tier] = tiers.get(item.tier, 0) + 1
        occurrences[item.tier] = occurrences.get(item.tier, 0) + item.occurrences
    stats = {
        "epub_bytes": size,
        "epub_name": args.out,
        "chapters": sum(1 for chapter in document.chapters if chapter.blocks),
        "blocks": sum(len(chapter.blocks) for chapter in document.chapters),
        "paragraphs": sum(1 for c in document.chapters for b in c.blocks if b.kind == "para"),
        "code_cells": sum(1 for c in document.chapters for b in c.blocks if b.kind == "code"),
        "figures": sum(1 for c in document.chapters for b in c.blocks if b.kind == "figure"),
        "tables": sum(1 for c in document.chapters for b in c.blocks if b.kind == "table"),
        "equations_display": sum(1 for c in document.chapters for b in c.blocks
                                 if b.kind == "display"),
        "images_embedded": len(figure_images),
        "math_items_by_tier": tiers,
        "math_occurrences_by_tier": occurrences,
        "math_svg": len(svg_manifest),
        "math_bitmap": len(math_images),
        "links_resolved": renderer.resolved,
        "links_unresolved": renderer.unresolved,
    }
    (WORK / "build_stats.json").write_text(json.dumps(stats, indent=1))
    print(f"wrote {target} ({size / 1024 / 1024:.1f} MB)")
    print(f"cross-references: {renderer.resolved} resolved, {renderer.unresolved} unresolved")
    print(f"stats: {WORK / 'build_stats.json'}")


if __name__ == "__main__":
    main()
