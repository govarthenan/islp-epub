"""Probe page layout: text column bounds, margin notes, headers/footers, code blocks,
and character-level detail needed to rebuild sub/superscript structure.

Run: uv run python src/probe_layout.py [page_numbers...]
"""

import sys
from collections import Counter
from pathlib import Path

import pymupdf

PDF_PATH = Path("ISLP_website.pdf")


def family(font_name: str) -> str:
    return font_name.split("+", 1)[-1]


def dump_page(doc: pymupdf.Document, page_index: int) -> None:
    page = doc[page_index]
    print(f"\n########## PAGE {page_index + 1} (rect={page.rect}) ##########")
    raw = page.get_text("rawdict")
    for block_index, block in enumerate(raw["blocks"]):
        if block["type"] != 0:
            print(f"  [IMAGE BLOCK {block_index}] bbox={tuple(round(v, 1) for v in block['bbox'])}")
            continue
        print(f"  [BLOCK {block_index}] bbox={tuple(round(v, 1) for v in block['bbox'])}")
        for line in block["lines"]:
            parts = []
            for span in line["spans"]:
                text = "".join(ch["c"] for ch in span["chars"])
                parts.append(f"<{family(span['font'])}|{span['size']:.1f}|o{span['origin'][1]:.1f}>{text}")
            print(
                f"    L y={line['bbox'][1]:.1f}-{line['bbox'][3]:.1f} x={line['bbox'][0]:.1f}-{line['bbox'][2]:.1f} "
                f"dir={line['dir']}"
            )
            print("      " + " ".join(parts))


def survey_columns(doc: pymupdf.Document) -> None:
    x0_hist: Counter[int] = Counter()
    x1_hist: Counter[int] = Counter()
    y_hist: Counter[int] = Counter()
    for page_index in range(0, doc.page_count):
        page = doc[page_index]
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                x0, y0, x1, y1 = line["bbox"]
                x0_hist[int(x0 // 5 * 5)] += 1
                x1_hist[int(x1 // 5 * 5)] += 1
                y_hist[int(y0 // 5 * 5)] += 1
    print("=== line x0 histogram (bucket of 5pt) ===")
    for bucket, count in sorted(x0_hist.items()):
        print(f"  {bucket:4d} {'#' * min(count // 200, 90)} {count}")
    print("=== line x1 histogram ===")
    for bucket, count in sorted(x1_hist.items()):
        print(f"  {bucket:4d} {'#' * min(count // 200, 90)} {count}")
    print("=== line y0 histogram ===")
    for bucket, count in sorted(y_hist.items()):
        print(f"  {bucket:4d} {'#' * min(count // 200, 90)} {count}")


def main() -> None:
    doc = pymupdf.open(PDF_PATH)
    args = sys.argv[1:]
    if not args:
        survey_columns(doc)
        return
    for arg in args:
        dump_page(doc, int(arg) - 1)


if __name__ == "__main__":
    main()
