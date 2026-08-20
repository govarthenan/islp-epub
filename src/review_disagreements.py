"""Lay the audit's disagreements out side by side, for a person to settle.

    uv run python src/review_disagreements.py
    uv run python src/review_disagreements.py m00001 m00130   # only these

`src/codex_audit.py` reports where the outside auditor says the transcription differs from the
page. It cannot be the last word: it sees the same crop the transcriber saw, so a crop that cut
the expression short looks exactly like a transcription that dropped a term. Only the printed
page settles that, which is why every disagreement is put in front of a person.

The comparison image the auditor read stacks the two halves, which is the right shape for a
model and the wrong one for an eye: a tall pair forces the reader to look away from one half to
find the other. This puts the page crop and the typeset candidate on one line instead, at a
common baseline scale, with the LaTeX and the auditor's complaint written underneath.

The candidate is drawn by CairoSVG here, not by MuPDF as in `render_candidates.py`. MuPDF
misplaces the nested viewport MathJax uses to stretch a tall bracket, so it draws every matrix
delimiter as a hook, a bar and another hook - which an auditor honestly reports as a changed
delimiter. This shows what the book actually ships.

Outputs work/math_disagreements/<id>.png, one file per disagreement, plus index.png holding
every pair in one column for a single scroll.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))

from islp.mathraster import svg_to_png_on_white  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
CROPS = WORK / "math_crops"
CANDIDATE_SVG = WORK / "math_candidate_svg"
OUT = WORK / "math_disagreements"

# Measured against the crops: the widest is 1,150 px, and half of a 2,560 px screen is 1,280,
# so a panel of 1,120 px holds every crop at its own size and still leaves room for the gutter.
PANEL = 1120
GUTTER = 28
MARGIN = 22
HEAD = 34
RULE = 150

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


LABEL_FONT = font(FONT_PATH, 20)
TITLE_FONT = font(FONT_PATH, 26)
BODY_FONT = font(FONT_PATH, 19)
MONO_FONT = font(MONO_PATH, 17)


# The crops come off the page at 300 ppi, where the book's 10 pt mathematics measures about
# 42 px to the em, so drawing the candidate at 42 puts the two halves at the same size.
PIXELS_PER_EM = 42


def rasterise(svg_path: Path) -> Image.Image:
    """Draw the candidate SVG the way the book draws it."""
    return Image.open(io.BytesIO(svg_to_png_on_white(svg_path.read_bytes(), PIXELS_PER_EM))).convert("L")


def fit(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = min(1.0, width / image.width, height / image.height) if image.height else 1.0
    if scale >= 1.0:
        return image
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)


def wrap(text: str, drawing: ImageDraw.ImageDraw, face: ImageFont.ImageFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if drawing.textlength(trial, font=face) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def pair(ident: str, issue: str, latex: str) -> Image.Image | None:
    crop_path = CROPS / f"{ident}.png"
    svg_path = CANDIDATE_SVG / f"{ident}.svg"
    if not crop_path.exists() or not svg_path.exists():
        return None

    crop = Image.open(crop_path).convert("L")
    candidate = rasterise(svg_path)
    tallest = max(crop.height, candidate.height, 1)
    ceiling = min(max(tallest, 60), 520)
    crop = fit(crop, PANEL, ceiling)
    candidate = fit(candidate, PANEL, ceiling)

    scratch = ImageDraw.Draw(Image.new("L", (1, 1)))
    text_width = PANEL * 2 + GUTTER
    issue_lines = wrap(f"codex: {issue}", scratch, BODY_FONT, text_width)
    latex_lines = wrap(latex, scratch, MONO_FONT, text_width)

    body = max(crop.height, candidate.height)
    height = MARGIN + HEAD + 10 + HEAD + body + 18 + len(issue_lines) * 26 + 8 + len(latex_lines) * 24 + MARGIN
    canvas = Image.new("L", (MARGIN * 2 + text_width, height), 255)
    painter = ImageDraw.Draw(canvas)

    y = MARGIN
    painter.text((MARGIN, y), ident, fill=0, font=TITLE_FONT)
    y += HEAD + 10
    painter.text((MARGIN, y), "THE PRINTED PAGE", fill=90, font=LABEL_FONT)
    painter.text((MARGIN + PANEL + GUTTER, y), "THE CANDIDATE, TYPESET", fill=90, font=LABEL_FONT)
    y += HEAD

    canvas.paste(crop, (MARGIN, y))
    canvas.paste(candidate, (MARGIN + PANEL + GUTTER, y))
    painter.line(
        [(MARGIN + PANEL + GUTTER // 2, y - 6), (MARGIN + PANEL + GUTTER // 2, y + body + 6)], fill=RULE, width=2
    )
    y += body + 18

    for line in issue_lines:
        painter.text((MARGIN, y), line, fill=40, font=BODY_FONT)
        y += 26
    y += 8
    for line in latex_lines:
        painter.text((MARGIN, y), line, fill=110, font=MONO_FONT)
        y += 24
    return canvas


def stack(images: list[Image.Image]) -> Image.Image:
    width = max(image.width for image in images)
    height = sum(image.height + 4 for image in images)
    canvas = Image.new("L", (width, height), 255)
    painter = ImageDraw.Draw(canvas)
    y = 0
    for image in images:
        canvas.paste(image, (0, y))
        y += image.height
        painter.line([(0, y + 1), (width, y + 1)], fill=RULE, width=2)
        y += 4
    return canvas


def main() -> None:
    report = json.loads((WORK / "codex_audit.json").read_text())
    wanted = set(sys.argv[1:])
    disagreements = [d for d in report.get("disagreements", []) if not wanted or d["id"] in wanted]
    if not disagreements:
        raise SystemExit("no disagreements to lay out")

    source = WORK / "math_final.json"
    if not source.exists():
        source = WORK / "math_transcription.json"
    latex = {ident: entry.get("latex", "") for ident, entry in json.loads(source.read_text()).items()}

    OUT.mkdir(parents=True, exist_ok=True)
    built = []
    for entry in disagreements:
        image = pair(entry["id"], entry.get("issue", ""), latex.get(entry["id"], ""))
        if image is None:
            print(f"  {entry['id']}: no crop or no candidate SVG")
            continue
        image.save(OUT / f"{entry['id']}.png", optimize=True)
        built.append(image)

    if built:
        stack(built).save(OUT / "index.png", optimize=True)
    print(f"{len(built)} pairs in {OUT}, and all of them in {OUT / 'index.png'}")


if __name__ == "__main__":
    main()
