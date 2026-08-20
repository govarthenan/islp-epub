"""Build the EPUB from the PDF.

    uv run python src/build_epub.py [--limit N] [--no-figures]

Stages:
  1. assemble the document model from the PDF
  2. render figures and tables to 300 ppi PNG, in colour
  3. render mathematics: LaTeX to SVG where LaTeX is known, cropped PNG otherwise
  4. write XHTML and package the EPUB, once for each variant
  5. write the build statistics

Two books come out of one pass over the PDF:

  output/ISLP.epub         mathematics as SVG. Sharp at every font size, and the ink follows
                           the reader's colour scheme.
  output/ISLP-raster.epub  the same mathematics as PNG, drawn from the same SVG files. For
                           Moon+ Reader and the Send-to-Kindle converter, which do not draw
                           SVG at all.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))

from islp.document import Document, assemble_document
from islp.epub import EpubBuilder, NavPoint, _escape
from islp.figures import render_region
from islp.mathraster import RASTER_RENDERER, svg_to_png

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "ISLP_website.pdf"
WORK = ROOT / "work"
OUTPUT = ROOT / "output"

FIGURE_DPI = 300
MATH_DPI = 400
# Pixels for one CSS em in the raster book. At 48 the mathematics stays sharp up to a large
# reading font, and the PNG costs about as many bytes as the SVG it stands in for.
MATH_PNG_PX_PER_EM = 48
GREY_LEVELS = 16
# The book plots one series in orange (152, 65, 0) and the next in blue (0, 104, 180). The
# two have almost the same luminance, 84 and 82 of 255, so a grey rendering paints them the
# same shade and the reader cannot tell the series apart. Figures therefore keep their
# colour, at a cost of about a fifth of the image bytes. A grey screen converts them itself,
# which is no worse than what a grey rendering gave it.
COLOUR_LEVELS = 64
BODY_POINT_SIZE = 10.0  # the book's body size; used to convert PDF points to em

MATH_TOKEN_RE = re.compile(r"\{\{MATH:(m\d+)\}\}")
LINK_ANCHOR_RE = re.compile(r'<a href="\{\{LINK:(\d+):(-?\d+)\}\}">(.*?)</a>', re.S)

TITLE = "An Introduction to Statistical Learning with Applications in Python"
AUTHORS = ["Gareth James", "Daniela Witten", "Trevor Hastie", "Robert Tibshirani", "Jonathan Taylor"]

CONVERTED_BY = "Govarthenan Rajadurai"
REPOSITORY = "https://github.com/govarthenan/islp-epub"

# A README stays on GitHub; this file goes to the device. So the rights statement and the
# caution about the machine-read mathematics are carried inside the book itself, on a page
# the reader meets before the first chapter. Only the classes already in the stylesheet are
# used here, so the page follows the reader's own typography and colour scheme like any other.
ABOUT_PAGE = f"""<h1>About this conversion</h1>

<p class="noindent">This is not the original book. It is a change of format: the publisher's
PDF, rebuilt as a reflowable EPUB so that it can be read on a small screen. The words, the
figures and the mathematics are the authors'.</p>

<h2>The book</h2>
<p class="noindent"><i>An Introduction to Statistical Learning, with Applications in
Python</i>, by {", ".join(AUTHORS[:-1])} and {AUTHORS[-1]}. Springer, 2023.</p>
<p><b>All rights in the text, the figures, the tables and the mathematics
remain with the authors and with Springer Nature.</b> They give the PDF away free of charge at
statlearning.com. Download it from there. It is the authority, and this conversion is not.</p>
<p>This edition is supplied for personal, educational and non-commercial use
only. Do not sell it, and do not charge for access to it. If you pass it on, keep this page
with it.</p>

<h2>Part of the mathematics was read by AI models</h2>
<p class="noindent">Most of the mathematics in this book was rebuilt by measurement, from the
character data in the PDF. But 531 expressions hold structure that a PDF does not record —
fractions, radicals, matrices, integrals — and those were cropped from the page and
transcribed by AI vision models.</p>
<p>Every one of the 531 was checked a second time against the printed page:
481 identical, 49 cosmetic differences, 1 wrong. The error was corrected. A sample was then
audited by a different model family, which found one further error that no check inside the
pipeline had caught.</p>
<p><b>That measured the error rate. It did not remove it.</b> Check any
equation against the free PDF before you rely on it for study, for an examination or for work.
If you find one that is wrong, please report it at the address below.</p>
<p>The figures and the tables were not transcribed this way. The figures are
re-rendered from the vector art in the PDF, and the tables were converted to text and checked
against the page.</p>

<h2>No warranty</h2>
<p class="noindent">This edition is supplied as it is. No promise is made that any expression,
figure, table or cross-reference is correct, or that this file opens correctly in any given
application.</p>

<h2>The conversion</h2>
<p class="noindent">The conversion was made by {CONVERTED_BY}. The pipeline, the engineering
journal and the full statement of rights are at:</p>
<p class="noindent">{REPOSITORY}</p>
<p>Corrections, and reports of a page that reads wrongly on your device, are
welcome there. If you hold rights in the book and you want this edition withdrawn, open an
issue at that address and it will be removed.</p>
"""


# ---------------------------------------------------------------------------------------
# image helpers
# ---------------------------------------------------------------------------------------


def pixmap_to_png(pix: pymupdf.Pixmap, levels: int = GREY_LEVELS) -> bytes:
    image = Image.frombytes("RGB" if pix.n >= 3 else "L", (pix.width, pix.height), pix.samples)
    if levels and levels < 256:
        image = image.quantize(colors=levels, method=Image.MEDIANCUT)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def render_crop(
    pdf_page: pymupdf.Page,
    bbox,
    dpi: int,
    pad: float = 1.0,
    foreign_ink: list | None = None,
    colour: bool = False,
) -> bytes:
    box = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    pix = render_region(pdf_page, box, dpi=dpi, colour=colour)
    image = Image.frombytes("RGB" if colour else "L", (pix.width, pix.height), pix.samples)
    if foreign_ink:
        scale = dpi / 72.0
        painter = ImageDraw.Draw(image)
        for fx0, fy0, fx1, fy1 in foreign_ink:
            painter.rectangle(
                [((fx0 - box[0]) * scale, (fy0 - box[1]) * scale), ((fx1 - box[0]) * scale, (fy1 - box[1]) * scale)],
                fill=(255, 255, 255) if colour else 255,
            )
    quantised = image.quantize(colors=COLOUR_LEVELS if colour else GREY_LEVELS, method=Image.MEDIANCUT)
    buffer = io.BytesIO()
    quantised.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


# ---------------------------------------------------------------------------------------
# mathematics
# ---------------------------------------------------------------------------------------


def load_table_html() -> dict[str, str]:
    path = WORK / "tables_html.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_verified_latex() -> dict[str, str]:
    """Prefer the verified file when it exists, otherwise the raw transcription."""
    for name in ("math_final.json", "math_transcription.json"):
        path = WORK / name
        if path.exists():
            data = json.loads(path.read_text())
            return {ident: entry["latex"] for ident, entry in data.items() if entry.get("latex")}
    return {}


def render_svgs(jobs: list[dict]) -> dict[str, dict]:
    if not jobs:
        return {}
    jobs_path = WORK / "math_jobs.json"
    out_dir = WORK / "math_svg"
    manifest_path = WORK / "math_svg_manifest.json"
    jobs_path.write_text(json.dumps(jobs))
    subprocess.run(
        ["node", str(ROOT / "src" / "render_math.cjs"), str(jobs_path), str(out_dir), str(manifest_path)],
        check=True,
        cwd=ROOT,
    )
    payload = json.loads(manifest_path.read_text())
    if payload["failures"]:
        (WORK / "math_svg_failures.json").write_text(json.dumps(payload["failures"], indent=1))
    return payload["manifest"]


# ---------------------------------------------------------------------------------------
# XHTML rendering
# ---------------------------------------------------------------------------------------


class Renderer:
    def __init__(
        self,
        document: Document,
        math_manifest: dict,
        math_images: dict,
        figure_images: dict,
        targets: dict | None = None,
        table_html: dict | None = None,
    ) -> None:
        self.document = document
        self.math_manifest = math_manifest
        self.math_images = math_images
        self.figure_images = figure_images
        self.table_html = table_html or {}
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
        entry = self.math_manifest.get(ident)
        if entry:
            height = entry["heightEm"] or 1.0
            valign = entry["valignEm"] or 0.0
            alt = _escape(entry["tex"])
            return (
                f'<img class="mi" src="../math/{entry["file"]}" alt="{alt}" '
                f'style="height:{height:.3f}em;vertical-align:{valign:.3f}em"/>'
            )
        name = self.math_images.get(ident)
        if name:
            x0, y0, x1, y1 = item.bbox
            width = (x1 - x0) / BODY_POINT_SIZE
            height = (y1 - y0) / BODY_POINT_SIZE
            alt = _escape(item.raw_text.strip() or "mathematical expression")
            return (
                f'<img class="mi" src="../images/{name}" alt="{alt}" '
                f'style="width:{width:.3f}em;height:{height:.3f}em"/>'
            )
        return _escape(item.raw_text)

    def expand(self, html: str) -> str:
        html = MATH_TOKEN_RE.sub(lambda m: self.inline_math(m.group(1)), html)
        return self.expand_links(html)

    def display_math(self, ident: str, eq_number: str) -> str:
        item = self.document.math.items[ident]
        entry = self.math_manifest.get(ident)
        if entry:
            width = entry["widthEm"] or 1.0
            alt = _escape(entry["tex"])
            body = f'<img src="../math/{entry["file"]}" alt="{alt}" style="width:{width:.3f}em"/>'
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


def table_key(block) -> str:
    return f"t{block.number.replace('.', '-')}-p{block.page + 1}"


ROMAN_MARKER_RE = re.compile(r"^\(?[ivxlcdm]+[.)]$")
LETTER_MARKER_RE = re.compile(r"^\(?[a-z]\)$")


def list_level(block) -> int:
    """Depth of an exercise item.

    The marker itself says which level it is - "1.", then "(a)", then "i." - and that is far
    steadier than the left margin, which drifts by twenty points from item to item. Only
    unmarked continuation paragraphs fall back to the measured indent."""
    marker = block.list_marker.strip()
    if marker:
        if ROMAN_MARKER_RE.match(marker):
            return 3
        if LETTER_MARKER_RE.match(marker):
            return 2
        return 1
    left = block.meta.get("left", 91.0)
    if left >= 150:
        return 3
    if left >= 132:
        return 2
    if left >= 108:
        return 1
    return 0


def paragraph_class(block) -> str:
    level = list_level(block)
    if block.list_marker:
        return {1: "li", 2: "li2", 3: "li3"}[level]
    if level:
        suffix = "-cont-in" if block.meta.get("indented", False) else "-cont"
        return {1: "li", 2: "li2", 3: "li3"}[level] + suffix
    return "" if block.meta.get("indented", False) else "noindent"


def render_chapter(chapter, renderer: Renderer, nav_children: list[NavPoint], href_base: str) -> str:
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
                number = f'<span class="chapnum">Chapter {_escape(chapter.number)}</span>' if chapter.number else ""
                parts.append(f'<h1 id="{anchor}">{number}{text}</h1>')
            else:
                level = min(max(block.level, 2), 5)
                parts.append(f'<h{level} id="{anchor}">{text}</h{level}>')
                if block.level in (2, 3):
                    # Entities must become characters again before the navigation document
                    # escapes them, or "p > 1" reaches the reader's contents as "p &amp;gt; 1".
                    nav_children.append(
                        NavPoint(
                            title=unescape(re.sub(r"<[^>]+>", "", text)),
                            level=block.level,
                            href=f"{href_base}#{anchor}",
                        )
                    )
            continue

        if block.kind == "para":
            css = paragraph_class(block)
            marker = f'<span class="marker">{_escape(block.list_marker)}</span> ' if block.list_marker else ""
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
            parts.append(f'<div class="codeblock"{ident}><pre class="{css}">{_escape(block.html)}</pre></div>')
            continue

        if block.kind in ("figure", "table"):
            name = renderer.figure_images.get((block.page, block.kind, block.number))
            caption = renderer.expand(block.html)
            caption = re.sub(
                r"^(<strong>)(FIGURE|TABLE)([^<]*)(</strong>)", r'<span class="label">\2\3</span>', caption, count=1
            )
            markup = renderer.table_html.get(table_key(block)) if block.kind == "table" else None
            if markup:
                image = markup
            else:
                image = f'<img src="../images/{name}" alt="{block.kind} {_escape(block.number)}"/>' if name else ""
            named = f"{block.kind[0]}{block.number.replace('.', '-')}"
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(
                f'<div class="figure"{ident}><span id="{named}"></span>{image}<p class="caption">{caption}</p></div>'
            )
            continue

        if block.kind == "footnote":
            ident = f' id="{anchor_id}"' if anchor_id else ""
            parts.append(f'<aside class="footnote" epub:type="footnote"{ident}>{renderer.expand(block.html)}</aside>')
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
# the two books
# ---------------------------------------------------------------------------------------

SVG_SUMMARY = (
    "The whole book is reflowable text, with chapter, section and index navigation. "
    "Tables are table markup, not pictures. Mathematics is scalable SVG whose alternative "
    "text carries the LaTeX source, so a screen reader speaks the LaTeX rather than the "
    "expression; there is no MathML. Figures are images with a short alternative text, "
    "followed by the printed caption as text. No audio, no video and nothing that flashes."
)

RASTER_SUMMARY = (
    "The whole book is reflowable text, with chapter, section and index navigation. "
    "Tables are table markup, not pictures. Mathematics is a picture sized in em, so it "
    "grows with the text, and its alternative text carries the LaTeX source, so a screen "
    "reader speaks the LaTeX rather than the expression; there is no MathML. Figures are "
    "images with a short alternative text, followed by the printed caption as text. "
    "No audio, no video and nothing that flashes."
)

# An SVG used as an image carries its own colour rules, written into every file by
# src/render_math.cjs. A PNG cannot carry a stylesheet, so the rule for the raster book
# lives here instead. A reader that repaints the page with CSS turns the ink over. A reader
# that inverts the whole screen, which is what e-ink devices do, matches nothing here and
# inverts the black itself, as it did before. Figures are left out of this rule on purpose:
# a photograph or a coloured plot must not be inverted.
RASTER_CSS = """
@media (prefers-color-scheme: dark) {
  div.eq img, img.mi { filter: invert(1); }
}
"""


@dataclass(frozen=True)
class Variant:
    """One of the books. They differ only in how the mathematics is carried.

    The SVG book is sharp at every font size and its ink follows the reader's colour scheme.
    Moon+ Reader on Android cannot draw SVG at all, and the Send-to-Kindle converter does not
    always keep it, so the raster book carries the same equations as PNG instead.
    """

    name: str
    out: str
    mathematics: str
    media_type: str
    source: Path
    prefix: str
    extra_css: str
    accessibility_summary: str


VARIANTS = {
    "svg": Variant(
        name="svg",
        out="ISLP.epub",
        mathematics="SVG",
        media_type="image/svg+xml",
        source=WORK / "math_svg",
        prefix="svg",
        extra_css="",
        accessibility_summary=SVG_SUMMARY,
    ),
    "raster": Variant(
        name="raster",
        out="ISLP-raster.epub",
        mathematics="PNG",
        media_type="image/png",
        source=WORK / "math_png",
        prefix="png",
        extra_css=RASTER_CSS,
        accessibility_summary=RASTER_SUMMARY,
    ),
}


@dataclass
class SharedAssets:
    """Everything that costs a pass over the PDF and is the same in both books."""

    resources: list[tuple[str, str, bytes, str, str]]
    dedication: str
    figure_images: dict[tuple, str]
    math_images: dict[str, str]
    targets: dict[int, list[tuple[float, float, str]]]
    table_html: dict[str, str]


def rasterise_math(svg_manifest: dict[str, dict], pixels_per_em: int) -> dict[str, dict]:
    """Draw every equation SVG as a PNG, and remember which ones are already drawn.

    `work/math_svg/` stays the one source of truth: the PNG is made from the SVG, never from
    the page, so the two books can never disagree about what an equation says. The cache is
    keyed by a hash of the SVG bytes, so an equation that did not change is not drawn again.

    A failure drops that identifier from the returned manifest. The caller then falls back to
    a crop of the printed page, exactly as it already does for an equation with no LaTeX.

    Args:
        svg_manifest: The manifest written by `render_svgs`.
        pixels_per_em: Pixels to use for one CSS em of the reader's text.

    Returns:
        The same manifest, with each `file` name pointing at the PNG.
    """
    out_dir = WORK / "math_png"
    out_dir.mkdir(exist_ok=True)
    cache_path = WORK / "math_png_cache.json"
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    # The cache is thrown away when the size changes, and also when the renderer changes: the
    # drawing depends on both, and a PNG drawn by an older renderer must not survive.
    if cached.get("pixels_per_em") != pixels_per_em or cached.get("renderer") != RASTER_RENDERER:
        cached = {"pixels_per_em": pixels_per_em, "renderer": RASTER_RENDERER, "files": {}}
    digests: dict[str, str] = cached["files"]

    manifest: dict[str, dict] = {}
    failures: list[dict] = []
    drawn = 0
    for ident, entry in svg_manifest.items():
        svg_bytes = (WORK / "math_svg" / entry["file"]).read_bytes()
        digest = hashlib.sha256(svg_bytes).hexdigest()[:16]
        png_path = out_dir / f"{ident}.png"
        if digests.get(ident) != digest or not png_path.exists():
            try:
                png_path.write_bytes(svg_to_png(svg_bytes, pixels_per_em))
            except Exception as error:  # noqa: BLE001 - a failure here must not pass unseen
                failures.append({"id": ident, "file": entry["file"], "error": str(error)})
                continue
            digests[ident] = digest
            drawn += 1
        manifest[ident] = {**entry, "file": f"{ident}.png"}

    cache_path.write_text(
        json.dumps({"pixels_per_em": pixels_per_em, "renderer": RASTER_RENDERER, "files": digests}, indent=1)
    )
    failure_path = WORK / "math_png_failures.json"
    failure_path.write_text(json.dumps(failures, indent=1))
    total = sum(path.stat().st_size for path in out_dir.glob("*.png"))
    print(
        f"    {len(manifest)} equations as PNG at {pixels_per_em} px/em "
        f"({drawn} drawn now, {total / 1024 / 1024:.1f} MB)",
        flush=True,
    )
    if failures:
        print(f"    WARNING: {len(failures)} equations failed to draw; see {failure_path}", flush=True)
    return manifest


def write_book(
    document: Document,
    variant: Variant,
    out_name: str,
    math_manifest: dict[str, dict],
    assets: SharedAssets,
) -> tuple[Renderer, int]:
    """Package one of the two books and return its renderer and its size in bytes."""
    builder = EpubBuilder(identifier="urn:uuid:990f1b6d-ee55-5049-8e97-87eaa392518e", title=TITLE)
    builder.authors = AUTHORS
    # The five authors keep dc:creator. The conversion is a contribution to this edition,
    # not authorship of the book, so it is recorded as a transcriber instead.
    builder.contributors = [(CONVERTED_BY, "trc")]
    builder.publisher = "Springer"
    builder.source = "ISLP_website.pdf (statlearning.com), first printing July 5 2023"
    builder.rights = (
        "Converted from the freely distributed PDF for personal, educational "
        "and non-commercial use only. All rights remain with the authors and "
        "publisher. Part of the mathematics was transcribed by AI vision models "
        "and verified against the printed page; check any equation against the "
        "original PDF before relying on it. See the About this conversion page."
    )
    builder.description = (
        "A reflowable conversion of the ISLP textbook: real paragraphs, scalable mathematics "
        "and reflowing tables, for any e-reader, tablet or phone."
    )
    builder.accessibility_summary = variant.accessibility_summary
    builder.extra_css = variant.extra_css

    for path, media_type, data, ident, properties in assets.resources:
        builder.add_resource(path, media_type, data, ident, properties)
    builder.set_cover("cover-image")

    for ident, entry in math_manifest.items():
        data = (variant.source / entry["file"]).read_bytes()
        builder.add_resource(f"math/{entry['file']}", variant.media_type, data, f"{variant.prefix}-{ident}")

    builder.add_document(
        "cover.xhtml", "Cover", '<div class="cover"><img src="../images/cover.png" alt="Cover"/></div>', "cover"
    )
    builder.nav.append(NavPoint("Cover", "text/cover.xhtml", 1))
    builder.add_document("about.xhtml", "About this conversion", ABOUT_PAGE, "about")
    builder.nav.append(NavPoint("About this conversion", "text/about.xhtml", 1))
    builder.add_document("dedication.xhtml", "Dedication", assets.dedication, "dedication")
    builder.nav.append(NavPoint("Dedication", "text/dedication.xhtml", 1))

    renderer = Renderer(
        document, math_manifest, assets.math_images, assets.figure_images, assets.targets, assets.table_html
    )
    for chapter in document.chapters:
        if not chapter.blocks:
            continue
        name = f"{chapter.ident}.xhtml"
        href = f"text/{name}"
        children: list[NavPoint] = []
        body = render_chapter(chapter, renderer, children, href)
        label = unescape(f"{chapter.number}. {chapter.title}" if chapter.number else chapter.title)
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

    target = OUTPUT / out_name
    builder.write(target)
    return renderer, target.stat().st_size


# ---------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="stop after this PDF page")
    parser.add_argument("--out", default=None, help="write one book under this name; needs a single variant")
    parser.add_argument(
        "--variants",
        default="svg,raster",
        help="which books to write: svg, raster, or both, separated by a comma",
    )
    parser.add_argument("--pixels-per-em", type=int, default=MATH_PNG_PX_PER_EM)
    args = parser.parse_args()

    chosen = [name.strip() for name in args.variants.split(",") if name.strip()]
    unknown = [name for name in chosen if name not in VARIANTS]
    if unknown:
        parser.error(f"unknown variant {unknown[0]!r}; choose from {', '.join(VARIANTS)}")
    if args.out and len(chosen) != 1:
        parser.error("--out names one file, so name one variant with --variants as well")

    WORK.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    print("1/5 assembling document model ...", flush=True)
    document = assemble_document(PDF, progress=True, last=args.limit)
    pdf = pymupdf.open(PDF)

    # --- the parts that cost a pass over the PDF, and are the same in both books ----------
    print("2/5 rendering figures and tables ...", flush=True)
    resources: list[tuple[str, str, bytes, str, str]] = []
    cover = pixmap_to_png(pdf[0].get_pixmap(dpi=170, colorspace=pymupdf.csRGB, alpha=False), levels=COLOUR_LEVELS)
    resources.append(("images/cover.png", "image/png", cover, "cover-image", "cover-image"))

    figure_images: dict[tuple, str] = {}
    available_tables = set(load_table_html())
    for chapter in document.chapters:
        for block in chapter.blocks:
            if block.kind not in ("figure", "table"):
                continue
            if block.bbox == (0, 0, 0, 0):
                continue
            if block.kind == "table" and table_key(block) in available_tables:
                continue  # markup replaces the picture
            name = f"{block.kind}-{block.number.replace('.', '-')}-p{block.page + 1}.png"
            data = render_crop(pdf[block.page], block.bbox, FIGURE_DPI, pad=2.0, colour=True)
            resources.append((f"images/{name}", "image/png", data, f"img-{name.replace('.', '-')}", ""))
            figure_images[(block.page, block.kind, block.number)] = name
    print(f"    {len(figure_images)} figures and tables", flush=True)

    # --- mathematics ---------------------------------------------------------------------
    print("3/5 rendering mathematics ...", flush=True)
    verified = load_verified_latex()
    jobs: list[dict] = []
    for ident, item in document.math.items.items():
        latex = verified.get(ident) or (item.latex if item.tier == "latex" else "")
        if latex:
            jobs.append({"id": ident, "tex": latex, "display": item.display})
    svg_manifest = render_svgs(jobs)
    manifests = {"svg": svg_manifest}
    if "raster" in chosen:
        manifests["raster"] = rasterise_math(svg_manifest, args.pixels_per_em)

    math_images: dict[str, str] = {}
    for ident, item in document.math.items.items():
        if ident in svg_manifest:
            continue
        if item.tier == "text":
            continue
        name = f"{ident}.png"
        data = render_crop(pdf[item.page], item.bbox, MATH_DPI, pad=0.8)
        resources.append((f"images/{name}", "image/png", data, f"img-{ident}", ""))
        math_images[ident] = name
    print(f"    {len(svg_manifest)} equations from LaTeX, {len(math_images)} as cropped images", flush=True)

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
                (float(y0), float(max(y1, y0 + 4)), f"{chapter.ident}.xhtml#{block.anchor}")
            )
    for entries in targets.values():
        entries.sort()

    table_html = load_table_html()
    print(
        f"    {len(table_html)} tables as markup, "
        f"{sum(1 for c in document.chapters for b in c.blocks if b.kind == 'table') - len(table_html)}"
        " as images",
        flush=True,
    )
    assets = SharedAssets(
        resources=resources,
        dedication=dedication_html(pdf),
        figure_images=figure_images,
        math_images=math_images,
        targets=targets,
        table_html=table_html,
    )

    # --- one book per variant --------------------------------------------------------------
    print(f"4/5 writing {len(chosen)} book(s) ...", flush=True)
    written: dict[str, dict] = {}
    renderer: Renderer | None = None
    for name in chosen:
        variant = VARIANTS[name]
        out_name = args.out or variant.out
        renderer, size = write_book(document, variant, out_name, manifests[name], assets)
        written[out_name] = {"bytes": size, "mathematics": variant.mathematics}
        print(f"    output/{out_name}: {size / 1024 / 1024:.1f} MB, mathematics as {variant.mathematics}", flush=True)

    # --- statistics -------------------------------------------------------------------------
    print("5/5 writing statistics ...", flush=True)
    primary = args.out or VARIANTS[chosen[0]].out
    tiers: dict[str, int] = {"text": document.math.text_runs}
    occurrences: dict[str, int] = {"text": document.math.text_runs}
    for item in document.math.items.values():
        tiers[item.tier] = tiers.get(item.tier, 0) + 1
        occurrences[item.tier] = occurrences.get(item.tier, 0) + item.occurrences
    stats = {
        "epub_bytes": written[primary]["bytes"],
        "epub_name": primary,
        "chapters": sum(1 for chapter in document.chapters if chapter.blocks),
        "blocks": sum(len(chapter.blocks) for chapter in document.chapters),
        "paragraphs": sum(1 for c in document.chapters for b in c.blocks if b.kind == "para"),
        "code_cells": sum(1 for c in document.chapters for b in c.blocks if b.kind == "code"),
        "figures": sum(1 for c in document.chapters for b in c.blocks if b.kind == "figure"),
        "tables": sum(1 for c in document.chapters for b in c.blocks if b.kind == "table"),
        "equations_display": sum(1 for c in document.chapters for b in c.blocks if b.kind == "display"),
        "images_embedded": len(figure_images),
        "tables_as_markup": len(table_html),
        "math_items_by_tier": tiers,
        "math_occurrences_by_tier": occurrences,
        "math_svg": len(svg_manifest),
        "math_png": len(manifests.get("raster", {})),
        "math_bitmap": len(math_images),
        "math_png_pixels_per_em": args.pixels_per_em,
        "variants": written,
        "links_resolved": renderer.resolved,
        "links_unresolved": renderer.unresolved,
    }
    (WORK / "build_stats.json").write_text(json.dumps(stats, indent=1))
    print(f"cross-references: {renderer.resolved} resolved, {renderer.unresolved} unresolved")
    print(f"stats: {WORK / 'build_stats.json'}")


if __name__ == "__main__":
    main()
