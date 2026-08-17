"""Compact per-line dump: position, dominant font, size, text. Used to design the block
classifier.

Run: uv run python src/probe_lines.py 45 46 120
"""

import sys
from collections import Counter
from pathlib import Path

import pymupdf

PDF_PATH = Path("ISLP_website.pdf")


def family(font_name: str) -> str:
    return font_name.split("+", 1)[-1]


def main() -> None:
    doc = pymupdf.open(PDF_PATH)
    for arg in sys.argv[1:]:
        page_index = int(arg) - 1
        page = doc[page_index]
        drawings = page.get_drawings()
        print(f"\n===== PAGE {page_index + 1}  drawings={len(drawings)} =====")
        if drawings:
            xs0 = min(d["rect"].x0 for d in drawings)
            ys0 = min(d["rect"].y0 for d in drawings)
            xs1 = max(d["rect"].x1 for d in drawings)
            ys1 = max(d["rect"].y1 for d in drawings)
            print(f"  drawings union bbox = ({xs0:.0f},{ys0:.0f})-({xs1:.0f},{ys1:.0f})")
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                print(f"  [IMG] {tuple(round(v) for v in block['bbox'])}")
                continue
            for line in block["lines"]:
                fonts: Counter[tuple[str, float]] = Counter()
                text_parts = []
                for span in line["spans"]:
                    fonts[(family(span["font"]), round(span["size"], 1))] += len(span["text"])
                    text_parts.append(span["text"])
                dominant = fonts.most_common(1)[0][0]
                x0, y0, x1, y1 = line["bbox"]
                text = "".join(text_parts)
                print(f"  x{x0:6.1f}-{x1:6.1f} y{y0:6.1f} {dominant[0]:>20s}/{dominant[1]:<5.1f} | {text[:110]}")


if __name__ == "__main__":
    main()
