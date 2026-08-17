"""Probe the ISLP PDF structure: outline, fonts per page, math-font usage, images.

Run: uv run python src/probe_structure.py
"""

import json
from collections import Counter
from pathlib import Path

import fitz

PDF_PATH = Path("ISLP_website.pdf")
OUT_DIR = Path("work")

# Computer Modern / AMS math font families used by LaTeX for mathematics.
MATH_FONT_MARKERS = ("CMMI", "CMSY", "CMEX", "MSBM", "MSAM", "CMBSY", "EUSM", "RSFS", "STMARY")


def font_family(font_name: str) -> str:
    """Strip the six-letter subset prefix (e.g. 'AAAABD+CMSY10' -> 'CMSY10')."""
    return font_name.split("+", 1)[-1]


def is_math_font(font_name: str) -> bool:
    fam = font_family(font_name).upper()
    return any(marker in fam for marker in MATH_FONT_MARKERS)


def main() -> None:
    doc = fitz.open(PDF_PATH)
    print(f"pages={doc.page_count}")

    toc = doc.get_toc()
    print(f"outline_entries={len(toc)}")
    for entry in toc[:40]:
        print("  ", entry)

    font_counter: Counter[str] = Counter()
    math_pages: Counter[int] = Counter()
    image_counter: Counter[int] = Counter()
    size_counter: Counter[float] = Counter()

    for page_index in range(doc.page_count):
        page = doc[page_index]
        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    fam = font_family(span["font"])
                    font_counter[fam] += len(span["text"])
                    size_counter[round(span["size"], 1)] += len(span["text"])
                    if is_math_font(span["font"]):
                        math_pages[page_index] += len(span["text"])
        image_counter[page_index] = len(page.get_images(full=True))

    print("\n=== font usage (chars) ===")
    for fam, count in font_counter.most_common(50):
        print(f"  {fam:30s} {count}")

    print("\n=== font sizes (chars) ===")
    for size, count in size_counter.most_common(20):
        print(f"  {size:6.1f} {count}")

    print(f"\npages_with_math_glyphs={sum(1 for v in math_pages.values() if v)}")
    print(f"total_math_glyphs={sum(math_pages.values())}")
    print(f"pages_with_images={sum(1 for v in image_counter.values() if v)}")
    print(f"total_embedded_images={sum(image_counter.values())}")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "probe_structure.json").write_text(
        json.dumps(
            {
                "page_count": doc.page_count,
                "toc": toc,
                "fonts": font_counter.most_common(),
                "sizes": sorted(size_counter.items()),
                "math_glyphs_per_page": math_pages.most_common(),
                "images_per_page": {k: v for k, v in image_counter.items() if v},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
