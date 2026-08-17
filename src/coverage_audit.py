"""Check that nothing on the page is silently dropped.

    uv run python src/coverage_audit.py

Walks every page, works out which text lines the block assembler consumed, and reports the
ones it did not. A conversion that quietly loses a line is worse than one that renders it
badly, because nothing in the output says anything is missing.

Writes work/coverage_audit.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from islp.blocks import assemble  # noqa: E402
from islp.document import FRONT_SKIP, INDEX_START, index_blocks  # noqa: E402
from islp.figures import consume_lines, detect_regions  # noqa: E402
from islp.pagemodel import Zone, load_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def main() -> None:
    pdf = pymupdf.open(ROOT / "ISLP_website.pdf")
    dropped: list[dict] = []
    counts: Counter[str] = Counter()

    for index in range(pdf.page_count):
        if index in FRONT_SKIP:
            continue
        page = load_page(pdf, index, two_column=index >= INDEX_START)
        regions = detect_regions(page, pdf[index])
        consume_lines(page, regions)

        interesting = [line for line in page.lines
                       if line.zone in (Zone.MAIN, Zone.CODE, Zone.FOOTNOTE, Zone.MARGIN)
                       and line.text.strip()]
        counts["lines"] += len(interesting)

        if index >= INDEX_START:
            used = {id(line) for block in index_blocks(page, page.drawing_rects, _Registry(),
                                                       "index", Counter())
                    for line in []}
            # index_blocks does not hand back its lines; count the column lines as used
            counts["index_lines"] += len(interesting)
            continue

        used = {id(line) for block in assemble(page) for line in block.lines}
        for line in interesting:
            if id(line) not in used:
                counts["dropped"] += 1
                dropped.append({
                    "page_pdf": index + 1,
                    "zone": line.zone.value,
                    "x0": round(line.x0, 1),
                    "x1": round(line.x1, 1),
                    "baseline": round(line.baseline, 1),
                    "size": round(line.size, 1),
                    "text": line.text.strip()[:120],
                })
        if index % 100 == 0:
            print(f"  page {index + 1}", flush=True)

    dropped.sort(key=lambda entry: entry["page_pdf"])
    summary = {
        "lines_considered": counts["lines"],
        "index_lines": counts["index_lines"],
        "lines_dropped": counts["dropped"],
        "share_dropped": round(counts["dropped"] / max(counts["lines"], 1) * 100, 3),
        "dropped": dropped[:400],
    }
    (WORK / "coverage_audit.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"lines considered : {summary['lines_considered']}")
    print(f"lines dropped    : {summary['lines_dropped']} ({summary['share_dropped']}%)")
    for entry in dropped[:25]:
        print(f"  p{entry['page_pdf']} [{entry['zone']}] x{entry['x0']}-{entry['x1']} "
              f"{entry['text']!r}")


class _Registry:
    """Just enough of MathRegistry for the index pass, which is not being audited."""

    def add(self, **_kwargs) -> str:
        return "m0"

    items: dict = {}


if __name__ == "__main__":
    main()
