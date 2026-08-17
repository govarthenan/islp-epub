"""Render candidate LaTeX and build side-by-side comparison images for verification.

    uv run python src/render_candidates.py work/math_transcription.json

For every candidate the LaTeX is typeset by MathJax, rasterised, and stacked under the
original crop from the PDF. A verifier then has to answer one concrete question — do these
two pictures say the same thing? — instead of transcribing from scratch, which is a much
easier question to get right and a much harder one to fake.

Outputs:
  work/math_compare/<id>.png     original above, rendering below
  work/math_render_failures.json LaTeX that MathJax refused to typeset
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
CROPS = WORK / "math_crops"
COMPARE = WORK / "math_compare"
CANDIDATE_SVG = WORK / "math_candidate_svg"

MAX_WIDTH = 1150
GAP = 26
LABEL_BAND = 0


def load_candidates(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        data = {entry["id"]: entry for entry in data}
    return {ident: entry["latex"] for ident, entry in data.items() if entry.get("latex")}


def render_svgs(candidates: dict[str, str], display: dict[str, bool]) -> dict[str, dict]:
    jobs = [{"id": ident, "tex": latex, "display": display.get(ident, True)} for ident, latex in candidates.items()]
    jobs_path = WORK / "math_candidate_jobs.json"
    manifest_path = WORK / "math_candidate_manifest.json"
    jobs_path.write_text(json.dumps(jobs))
    subprocess.run(
        ["node", str(ROOT / "src" / "render_math.cjs"), str(jobs_path), str(CANDIDATE_SVG), str(manifest_path)],
        check=True,
        cwd=ROOT,
    )
    payload = json.loads(manifest_path.read_text())
    (WORK / "math_render_failures.json").write_text(json.dumps(payload["failures"], indent=1))
    return payload["manifest"]


def rasterise(svg_path: Path, target_width: int) -> Image.Image:
    document = pymupdf.open(str(svg_path))
    page = document[0]
    zoom = max(0.2, min(12.0, target_width / max(page.rect.width, 1.0)))
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)


def compose(original: Image.Image, rendered: Image.Image) -> Image.Image:
    width = max(original.width, rendered.width)
    height = original.height + rendered.height + GAP
    canvas = Image.new("L", (width, height), 255)
    canvas.paste(original, (0, 0))
    canvas.paste(rendered, (0, original.height + GAP))
    painter = ImageDraw.Draw(canvas)
    line_y = original.height + GAP // 2
    painter.line([(0, line_y), (width, line_y)], fill=140, width=2)
    return canvas


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK / "math_transcription.json"
    candidates = load_candidates(source)
    jobs = {job["id"]: job for job in json.loads((WORK / "math_jobs_vlm.json").read_text())}
    display = {ident: jobs.get(ident, {}).get("kind", "display") == "display" for ident in candidates}

    print(f"typesetting {len(candidates)} candidates ...", flush=True)
    manifest = render_svgs(candidates, display)

    COMPARE.mkdir(parents=True, exist_ok=True)
    built = 0
    for ident, entry in manifest.items():
        crop_path = CROPS / f"{ident}.png"
        if not crop_path.exists():
            continue
        original = Image.open(crop_path).convert("L")
        scale = min(1.0, MAX_WIDTH / original.width)
        if scale < 1.0:
            original = original.resize((int(original.width * scale), int(original.height * scale)), Image.LANCZOS)
        rendered = rasterise(CANDIDATE_SVG / entry["file"], original.width)
        if rendered.width > MAX_WIDTH:
            factor = MAX_WIDTH / rendered.width
            rendered = rendered.resize((MAX_WIDTH, max(1, int(rendered.height * factor))), Image.LANCZOS)
        compose(original, rendered).save(COMPARE / f"{ident}.png", optimize=True)
        built += 1

    failures = json.loads((WORK / "math_render_failures.json").read_text())
    print(f"{built} comparison images in {COMPARE}")
    print(f"{len(failures)} candidates failed to typeset")


if __name__ == "__main__":
    main()
