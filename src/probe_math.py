"""Probe math regions: how many inline runs vs display equations, and their complexity.

Math in this book is typeset with Computer Modern math fonts (CM*/MSBM), while prose uses
Latin Modern (LM*). That gives a clean font-family split between mathematics and text.

Run: uv run python src/probe_math.py
"""

import json
from collections import Counter
from pathlib import Path

import pymupdf

PDF_PATH = Path("ISLP_website.pdf")
OUT_DIR = Path("work")

MATH_FONT_PREFIXES = ("CM", "MSBM", "MSAM", "EUSM", "RSFS", "STMARY", "LASY", "LINE")
# CMR/CMTT also appear in prose contexts rarely; treat all CM* as math for this probe.


def family(font_name: str) -> str:
    return font_name.split("+", 1)[-1]


def is_math(font_name: str) -> bool:
    fam = family(font_name).upper()
    return any(fam.startswith(p) for p in MATH_FONT_PREFIXES)


def main() -> None:
    doc = pymupdf.open(PDF_PATH)

    inline_runs: list[dict] = []
    display_runs: list[dict] = []
    run_len_hist: Counter[int] = Counter()
    sample_texts: list[str] = []

    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_width = page.rect.width
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans = line["spans"]
                math_chars = sum(len(s["text"]) for s in spans if is_math(s["font"]))
                total_chars = sum(len(s["text"]) for s in spans)
                if math_chars == 0:
                    continue
                line_text = "".join(s["text"] for s in spans)
                x0, _, x1, _ = line["bbox"]
                centred = abs((x0 + x1) / 2 - page_width / 2) < 18 and x0 > 90
                is_display = centred and math_chars / max(total_chars, 1) > 0.55
                record = {
                    "page": page_index,
                    "bbox": line["bbox"],
                    "text": line_text,
                    "math_chars": math_chars,
                    "total_chars": total_chars,
                }
                if is_display:
                    display_runs.append(record)
                else:
                    inline_runs.append(record)
                    # count contiguous math span runs inside the line
                    current = 0
                    for span in spans:
                        if is_math(span["font"]):
                            current += len(span["text"])
                        elif current:
                            run_len_hist[current] += 1
                            current = 0
                    if current:
                        run_len_hist[current] += 1
                if len(sample_texts) < 60 and math_chars > 6:
                    sample_texts.append(f"p{page_index + 1} [{'D' if is_display else 'I'}] {line_text}")

    print(f"lines_containing_math={len(inline_runs) + len(display_runs)}")
    print(f"display_math_lines={len(display_runs)}")
    print(f"inline_math_lines={len(inline_runs)}")
    print(f"inline_math_runs={sum(run_len_hist.values())}")
    print("\ninline run length histogram (glyphs -> count):")
    for length in sorted(run_len_hist):
        print(f"  {length:3d}: {run_len_hist[length]}")

    print("\n=== samples ===")
    for text in sample_texts:
        print(text)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "probe_math.json").write_text(
        json.dumps(
            {
                "display_count": len(display_runs),
                "inline_line_count": len(inline_runs),
                "run_len_hist": dict(sorted(run_len_hist.items())),
                "display_samples": display_runs[:40],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
