"""Check that the raster mathematics is drawn completely.

    uv run python src/check_math_raster.py [--sample 60] [--contact-sheet]

The raster book draws each equation from its MathJax SVG with CairoSVG. A renderer can fail
quietly: the equation still looks like an equation, and nothing complains. These checks
measure the drawing directly.

  1. Every equation must carry ink, and enough of it for its size. This runs over all of them.
  2. On a sample, the same SVG is drawn twice: once as MathJax wrote it, and once with every
     `<use>` replaced by the `<path>` it points at. The two must come out the same image. If
     they do not, the renderer is not following the glyph references properly.
  3. On the same sample, the `<defs>` are removed. The image must then be empty, except for
     the equations that also hold a `<rect>`: MathJax draws a fraction bar and a radical rule
     as a rectangle, not as a glyph, so ink from those is correct. This proves the ink really
     comes from the referenced glyphs and not from somewhere else.

  4. Every equation that stretches a bracket is drawn onto its own sheet,
     `work/math_stretchy_sheet.png`, for a person to look at. There are 40 of them in this
     book, and a stretched bracket is the thing a renderer gets wrong.

Checks 1 to 3 compare a renderer against itself. All three passed while every bracket around a
matrix was being drawn broken by MuPDF, which is why check 4 exists and why it asks for eyes.

Drawing each equation a second time with MuPDF and comparing the two was tried as an automatic
test, and dropped. Measured over 60 equations, ordinary ones differ from each other by as much
as 0.82 of their ink, only from how the two renderers smooth an edge, while the broken brackets
differed by 0.13 to 0.33. The two cannot be told apart that way, and a test that reports 58
faults out of 60 hides the one that is real.

The crops in `work/math_crops/` are not used. They come from an earlier pass with its own
numbering, and 154 of the 712 that share a name with an equation are of a different region of
the page, so a comparison against them would report faults that are not there.

Writes `work/math_raster_check.json`, and with `--contact-sheet` also
`work/math_raster_sheet.png`, a grid of the sampled equations for a person to look at.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))

from islp.mathraster import svg_to_png

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

MIN_INK_PER_EM2 = 0.02  # an equation with less ink than this for its size is suspect

PATH_RE = re.compile(r'<path id="([^"]+)" d="([^"]*)"\s*>\s*</path>|<path id="([^"]+)" d="([^"]*)"\s*/>')
USE_RE = re.compile(r"<use\b([^>]*?)\s*/?>(?:\s*</use>)?")
HREF_RE = re.compile(r'xlink:href="#([^"]+)"')
DEFS_RE = re.compile(r"<defs>.*?</defs>", re.S)
NESTED_SVG_RE = re.compile(rb"<svg\b[^>]*>.*?<svg\b", re.S)


def ink(image: Image.Image) -> float:
    """Ink of an image in whole pixels, counting partly covered pixels."""
    alpha = image.convert("LA").split()[1]
    return sum(alpha.histogram()[value] * value for value in range(256)) / 255.0


def ink_of_png(data: bytes) -> float:
    return ink(Image.open(io.BytesIO(data)))


def glyph_paths(svg: str) -> dict[str, str]:
    """The `d` of every glyph defined in `<defs>`, by its identifier."""
    found: dict[str, str] = {}
    for match in PATH_RE.finditer(svg):
        ident = match.group(1) or match.group(3)
        drawing = match.group(2) if match.group(1) else match.group(4)
        found[ident] = drawing
    return found


def expand_uses(svg: str) -> tuple[str, int]:
    """Replace every `<use>` with the glyph it points at, drawn in place.

    MathJax gives no `x` or `y` to a `<use>`; the position comes from the group around it. The
    substitution is therefore exact, and the drawing must not move by one pixel.
    """
    paths = glyph_paths(svg)
    replaced = 0

    def swap(match: re.Match) -> str:
        nonlocal replaced
        attributes = match.group(1)
        href = HREF_RE.search(attributes)
        if not href or href.group(1) not in paths:
            return match.group(0)
        if " x=" in attributes or " y=" in attributes:
            return match.group(0)  # a placed copy; leave it and let the check see the change
        keep = re.search(r'transform="([^"]*)"', attributes)
        transform = f' transform="{keep.group(1)}"' if keep else ""
        replaced += 1
        return f'<path d="{paths[href.group(1)]}"{transform}/>'

    return USE_RE.sub(swap, svg), replaced


def difference(first: bytes, second: bytes) -> float:
    """How much two drawings differ, as a fraction of the ink in the first.

    Two renderers round the pixel size differently, by a pixel or two, so the second drawing
    is brought to the size of the first before they are compared. Only the alpha channel is
    compared, because that is where the ink is.
    """
    one = Image.open(io.BytesIO(first)).convert("LA")
    two = Image.open(io.BytesIO(second)).convert("LA")
    if two.size != one.size:
        two = two.resize(one.size, Image.LANCZOS)
    changed = ImageChops.difference(one.split()[1], two.split()[1])
    total = ink(one)
    return (sum(changed.histogram()[value] * value for value in range(256)) / 255.0) / total if total else 1.0


def sample_ids(manifest: dict[str, dict], count: int) -> list[str]:
    """Take a spread of equations: display and inline, narrow and wide."""
    display = sorted((entry["widthEm"] or 0, ident) for ident, entry in manifest.items() if entry["display"])
    inline = sorted((entry["widthEm"] or 0, ident) for ident, entry in manifest.items() if not entry["display"])
    chosen: list[str] = []
    for group in (display, inline):
        if not group:
            continue
        want = min(count // 2, len(group))
        step = max(1, len(group) // want)
        chosen.extend(ident for _, ident in group[::step][:want])
    return chosen


def contact_sheet(rows: list[tuple[str, bytes]], target: Path, columns: int = 4) -> None:
    """A grid of the sampled equations, each under its identifier, for a human to read."""
    cell_width, cell_height, label = 460, 190, 16
    lines = (len(rows) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, lines * (cell_height + label)), "white")
    painter = ImageDraw.Draw(sheet)
    for index, (ident, data) in enumerate(rows):
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        scale = min(cell_width / image.width, cell_height / image.height, 1.0)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        x = (index % columns) * cell_width
        y = (index // columns) * (cell_height + label)
        white = Image.new("RGBA", image.size, (255, 255, 255, 255))
        white.alpha_composite(image)
        sheet.paste(white.convert("RGB"), (x + 4, y + label + (cell_height - image.height) // 2))
        painter.text((x + 4, y + 2), ident, fill="black")
    sheet.save(target, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=60, help="how many equations to test in depth")
    parser.add_argument("--pixels-per-em", type=int, default=48)
    parser.add_argument("--contact-sheet", action="store_true", help="also write a grid of the sample")
    args = parser.parse_args()

    manifest = json.loads((WORK / "math_svg_manifest.json").read_text())["manifest"]
    problems: list[str] = []

    # 1. every equation carries ink, and enough of it for its size
    print(f"1/3 checking the ink of all {len(manifest)} equations ...", flush=True)
    thin: list[dict] = []
    stretchy_ids: list[str] = []
    stretchy_rows: list[tuple[str, bytes]] = []
    for ident, entry in manifest.items():
        raw = (WORK / "math_svg" / entry["file"]).read_bytes()
        png = svg_to_png(raw, args.pixels_per_em)
        if NESTED_SVG_RE.search(raw):
            stretchy_ids.append(ident)
            stretchy_rows.append((ident, png))
        area_em2 = ink_of_png(png) / (args.pixels_per_em**2)
        box = (entry["widthEm"] or 1.0) * (entry["heightEm"] or 1.0)
        if area_em2 <= 0 or area_em2 / box < MIN_INK_PER_EM2:
            thin.append(
                {"id": ident, "ink_em2": round(area_em2, 4), "box_em2": round(box, 3), "tex": entry["tex"][:80]}
            )
    if thin:
        problems.append(f"{len(thin)} equations carry too little ink for their size")

    # 2 and 3. the sample, in depth
    print(f"2/3 following the glyph references on {args.sample} equations ...", flush=True)
    chosen = sample_ids(manifest, args.sample)
    sheet_rows: list[tuple[str, bytes]] = []
    reference_failures: list[dict] = []
    defs_failures: list[dict] = []
    for ident in chosen:
        svg = (WORK / "math_svg" / manifest[ident]["file"]).read_text()
        original = svg_to_png(svg.encode("utf-8"), args.pixels_per_em)
        sheet_rows.append((ident, original))

        expanded, replaced = expand_uses(svg)
        if replaced:
            drift = difference(original, svg_to_png(expanded.encode("utf-8"), args.pixels_per_em))
            if drift > 0.01:
                reference_failures.append({"id": ident, "replaced": replaced, "difference": round(drift, 4)})

        # A fraction bar and a radical rule are rectangles, not glyphs, so they survive on
        # purpose. Only an equation with no rectangle must come out completely empty.
        if "<rect" not in svg:
            stripped = DEFS_RE.sub("", svg)
            if ink_of_png(svg_to_png(stripped.encode("utf-8"), args.pixels_per_em)) > 0:
                defs_failures.append({"id": ident, "note": "ink remains after the glyph definitions are removed"})
    if reference_failures:
        problems.append(f"{len(reference_failures)} equations change when a <use> is replaced by its glyph")
    if defs_failures:
        problems.append(f"{len(defs_failures)} equations still carry ink without their glyph definitions")

    print("3/3 writing the report ...", flush=True)
    with_rules = sum(1 for ident in chosen if "<rect" in (WORK / "math_svg" / manifest[ident]["file"]).read_text())
    payload = {
        "equations": len(manifest),
        "pixels_per_em": args.pixels_per_em,
        "sampled_in_depth": len(chosen),
        "sampled_with_a_rule": with_rules,
        "too_thin": thin,
        "reference_failures": reference_failures,
        "defs_failures": defs_failures,
        "with_a_stretched_bracket": stretchy_ids,
    }
    (WORK / "math_raster_check.json").write_text(json.dumps(payload, indent=1))

    print()
    print(f"  equations drawn           {len(manifest)}")
    print(f"  too little ink            {len(thin)}")
    print(f"  glyph references followed {len(chosen) - len(reference_failures)} of {len(chosen)}")
    print(f"  ink comes from the glyphs {len(chosen) - len(defs_failures) - with_rules} of {len(chosen) - with_rules}")
    print(f"                            ({with_rules} of the sample hold a rule and are exempt)")
    print(f"  stretch a bracket         {len(stretchy_ids)}, on their own sheet for a person to check")
    if args.contact_sheet:
        target = WORK / "math_raster_sheet.png"
        contact_sheet(sheet_rows, target)
        print(f"  contact sheet             {target}")
        stretchy_target = WORK / "math_stretchy_sheet.png"
        contact_sheet(stretchy_rows, stretchy_target, columns=3)
        print(f"  stretched brackets        {stretchy_target}")
    print(f"  report                    {WORK / 'math_raster_check.json'}")
    if problems:
        print("\nPROBLEMS:")
        for line in problems:
            print(f"  {line}")
        sys.exit(1)
    print("\nno problems")


if __name__ == "__main__":
    main()
