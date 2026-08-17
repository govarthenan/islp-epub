"""Cut each table out of the PDF as an image, for conversion to real HTML.

    uv run python src/extract_table_jobs.py

A table rendered as a picture cannot reflow and cannot follow the reader's font size, which
matters on a 7 inch screen. There are only 38 of them, so each one is read back as markup.

Outputs:
  work/table_crops/<key>.png
  work/table_jobs.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from build_epub import render_crop  # noqa: E402
from islp.document import assemble_document  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
CROPS = WORK / "table_crops"
DPI = 320


def strip_tags(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html)


def main() -> None:
    CROPS.mkdir(parents=True, exist_ok=True)
    document = assemble_document(ROOT / "ISLP_website.pdf", progress=True)
    pdf = pymupdf.open(ROOT / "ISLP_website.pdf")

    jobs = []
    for chapter in document.chapters:
        for block in chapter.blocks:
            if block.kind != "table" or block.bbox == (0, 0, 0, 0):
                continue
            key = f"t{block.number.replace('.', '-')}-p{block.page + 1}"
            crop = CROPS / f"{key}.png"
            crop.write_bytes(render_crop(pdf[block.page], block.bbox, DPI, pad=3.0))
            jobs.append({
                "key": key,
                "image": str(crop.relative_to(ROOT)),
                "number": block.number,
                "page_pdf": block.page + 1,
                "chapter": chapter.title,
                "caption": strip_tags(block.html)[:400],
                "width_pt": round(block.bbox[2] - block.bbox[0], 1),
                "height_pt": round(block.bbox[3] - block.bbox[1], 1),
            })

    (WORK / "table_jobs.json").write_text(json.dumps(jobs, indent=1, ensure_ascii=False))
    print(f"{len(jobs)} tables cropped to {CROPS}")


if __name__ == "__main__":
    main()
