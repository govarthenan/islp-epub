"""Cut every piece of mathematics that needs a vision model out of the PDF as an image, and
write a manifest carrying the metadata that makes the reading job tractable.

    uv run python src/extract_math_jobs.py

Produces:
  work/math_crops/<id>.png      the cropped expression, 400 ppi, black on white
  work/math_jobs_vlm.json       one record per crop: chapter, page, equation number, the
                                characters the extractor could see, the deterministic LaTeX
                                guess where one exists, and the sentence that precedes it

The characters and the guess matter: they give the model the exact symbol inventory, so the
job becomes "reconstruct the structure" rather than "read this picture from nothing".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from build_epub import MATH_DPI, render_crop  # noqa: E402
from islp.document import assemble_document  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "ISLP_website.pdf"
WORK = ROOT / "work"
CROPS = WORK / "math_crops"


def main() -> None:
    CROPS.mkdir(parents=True, exist_ok=True)
    print("assembling document ...", flush=True)
    document = assemble_document(PDF, progress=True)

    chapter_titles = {chapter.ident: (chapter.number, chapter.title) for chapter in document.chapters}

    pdf = pymupdf.open(PDF)
    jobs = []
    for ident, item in document.math.items.items():
        if item.tier == "text":
            continue
        if item.tier == "latex" and item.latex:
            continue  # already solved deterministically
        number, title = chapter_titles.get(item.chapter, ("", ""))
        crop = CROPS / f"{ident}.png"
        crop.write_bytes(render_crop(pdf[item.page], item.bbox, MATH_DPI, pad=1.0, foreign_ink=item.foreign_ink))
        jobs.append(
            {
                "id": ident,
                "image": str(crop.relative_to(ROOT)),
                "kind": "display" if item.display else "inline",
                "page_pdf": item.page + 1,
                "chapter_number": number,
                "chapter_title": title,
                "equation_number": item.eq_number,
                "extracted_characters": item.raw_text,
                "deterministic_guess": item.meta_guess or item.latex,
                "why_model_needed": item.reason,
                "context_before": item.context[-400:],
                "occurrences": item.occurrences,
                "width_pt": round(item.bbox[2] - item.bbox[0], 1),
                "height_pt": round(item.bbox[3] - item.bbox[1], 1),
            }
        )

    (WORK / "math_jobs_vlm.json").write_text(json.dumps(jobs, indent=1, ensure_ascii=False))
    display_count = sum(1 for job in jobs if job["kind"] == "display")
    print(f"{len(jobs)} crops written ({display_count} display, {len(jobs) - display_count} inline)")
    print(f"manifest: {WORK / 'math_jobs_vlm.json'}")


if __name__ == "__main__":
    main()
