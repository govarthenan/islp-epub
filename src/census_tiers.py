"""Census of math-run tiers across the whole book, to size the vision-model job."""

import json
import sys
from collections import Counter
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from islp.inline import Tier, build_inline
from islp.pagemodel import Zone, load_page


def main() -> None:
    doc = pymupdf.open("ISLP_website.pdf")
    tiers: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    keys: dict[str, Counter[str]] = {t.value: Counter() for t in Tier}
    samples: dict[str, list[str]] = {t.value: [] for t in Tier}

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else doc.page_count
    for index in range(limit):
        page = load_page(doc, index)
        rules = page.drawing_rects
        for line in page.lines:
            if line.zone != Zone.MAIN:
                continue
            result = build_inline(line.chars, rules)
            for run in result.math_runs:
                tiers[run.tier.value] += 1
                reasons[run.reason] += 1
                keys[run.tier.value][run.key] += 1
                if len(samples[run.tier.value]) < 25:
                    samples[run.tier.value].append(f"p{index+1} {run.raw_text!r} -> {run.latex!r}")
            # TEXT-tier runs are inlined, count them by re-walking
    print("tiers:", dict(tiers))
    print("reasons:", dict(reasons))
    for tier in ("latex", "vlm"):
        print(f"\n{tier}: {tiers[tier]} occurrences, {len(keys[tier])} distinct")
        for sample in samples[tier][:20]:
            print("   ", sample)
    Path("work/tier_census.json").write_text(json.dumps(
        {"tiers": dict(tiers), "reasons": dict(reasons),
         "distinct": {k: len(v) for k, v in keys.items()},
         "top_latex": keys["latex"].most_common(40),
         "top_vlm": keys["vlm"].most_common(40)}, indent=2))


if __name__ == "__main__":
    main()
